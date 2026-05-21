from __future__ import annotations

import io
import json as json_module
import logging
import re
import zipfile
from typing import Any

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from flask.typing import ResponseReturnValue

from workflow_designer import config
from workflow_designer.models import FlowDefinition, MpiOutboundFlowDefinition
from workflow_designer.services.flow_store import FlowStore
from workflow_designer.services.graph_extractor import extract_flow_from_graph
from workflow_designer.services.tf_generator import (
    generate_flow_tf,
    generate_locals_snippet,
    generate_subscription_flow_tf,
    generate_subscription_locals_snippet,
    generate_subscription_variables_snippet,
    generate_variables_snippet,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s %(message)s")
log = logging.getLogger(__name__)

FLOW_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
store = FlowStore()


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    @app.context_processor
    def inject_global_context() -> dict[str, str]:
        return {"app_version": config.APP_VERSION}

    @app.get("/")
    def index() -> ResponseReturnValue:
        flows = store.get_all()
        return render_template("index.html", flows=flows)

    @app.get("/designer")
    def designer() -> ResponseReturnValue:
        """Canvas-based drag-and-drop workflow designer."""
        existing_flows = store.get_all()
        return render_template("designer.html", existing_flows=existing_flows)

    @app.post("/designer/preview")
    def designer_preview() -> ResponseReturnValue:
        """
        Preview-only endpoint. Accepts a Drawflow graph JSON + flow_id.
        Returns generated Terraform content and a resource summary as JSON.
        Nothing is saved, no Azure resources are created, no Terraform is run.
        """
        body = request.get_json(silent=True) or {}
        flow_id = str(body.get("flow_id", "")).strip().lower()
        graph_data = body.get("graph", {})
        log.debug("Received designer preview payload (%s chars)", len(json_module.dumps(graph_data)))

        flow, errors = extract_flow_from_graph(graph_data, flow_id)
        if errors:
            return {"ok": False, "errors": errors}, 400
        if flow is None:
            return {"ok": False, "errors": ["Unable to extract a flow from the supplied graph."]}, 400

        preview_files = _generate_preview_files(flow)
        return {
            "ok": True,
            "flow_id": flow_id,
            "flow_tf": preview_files["flow_tf"],
            "locals_snippet": preview_files["locals_snippet"],
            "variables_snippet": preview_files["variables_snippet"],
            "summary": _build_resource_summary(flow),
        }

    @app.route("/designer/preview-zip", methods=["GET", "POST"])
    def designer_preview_zip() -> ResponseReturnValue:
        """Generate and download a zip of TF files from a canvas graph (preview-only, no saving)."""
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
            flow_id = str(body.get("flow_id", "")).strip().lower()
            graph_data = body.get("graph", {})
        else:
            flow_id = request.args.get("flow_id", "").strip().lower()
            try:
                graph_data = json_module.loads(request.args.get("graph", "{}"))
            except ValueError:
                abort(400)

        flow, errors = extract_flow_from_graph(graph_data, flow_id)
        if errors or flow is None:
            abort(400)

        preview_files = _generate_preview_files(flow)
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"flow_{flow.flow_var_name}.tf", preview_files["flow_tf"])
            archive.writestr("locals_additions.tf", preview_files["locals_snippet"])
            archive.writestr("variables_additions.tf", preview_files["variables_snippet"])
        archive_buffer.seek(0)
        return send_file(
            archive_buffer,
            as_attachment=True,
            download_name=f"{flow.flow_var_name}_terraform_preview.zip",
            mimetype="application/zip",
        )

    @app.route("/flows/new", methods=["GET", "POST"])
    def new_flow() -> ResponseReturnValue:
        if request.method == "POST":
            flow, form_data = _flow_from_request()
            if flow is not None:
                store.save(flow)
                flash(f"Generated Terraform package for {flow.flow_id}.", "success")
                return redirect(url_for("view_flow", flow_id=flow.flow_id))
            return render_template(
                "flow_form.html",
                flow=None,
                form_data=form_data,
                is_edit=False,
                title="Create New Flow",
            )

        return render_template(
            "flow_form.html",
            flow=None,
            form_data=_default_form_data(),
            is_edit=False,
            title="Create New Flow",
        )

    @app.route("/flows/<flow_id>/edit", methods=["GET", "POST"])
    def edit_flow(flow_id: str) -> ResponseReturnValue:
        flow = store.get(flow_id)
        if flow is None:
            flash(f"Flow {flow_id} was not found.", "danger")
            return redirect(url_for("index"))
        if flow.readonly:
            flash("Read-only flows cannot be edited.", "warning")
            return redirect(url_for("view_flow", flow_id=flow_id))

        if request.method == "POST":
            updated_flow, form_data = _flow_from_request(existing_flow_id=flow_id)
            if updated_flow is not None:
                store.save(updated_flow)
                if updated_flow.flow_id != flow_id:
                    store.delete(flow_id)
                flash(f"Updated flow {updated_flow.flow_id}.", "success")
                return redirect(url_for("view_flow", flow_id=updated_flow.flow_id))
            return render_template(
                "flow_form.html",
                flow=flow,
                form_data=form_data,
                is_edit=True,
                title=f"Edit {flow.flow_id}",
            )

        return render_template(
            "flow_form.html",
            flow=flow,
            form_data=_flow_to_form_data(flow),
            is_edit=True,
            title=f"Edit {flow.flow_id}",
        )

    @app.get("/flows/<flow_id>")
    def view_flow(flow_id: str) -> ResponseReturnValue:
        flow = store.get(flow_id)
        if flow is None:
            flash(f"Flow {flow_id} was not found.", "danger")
            return redirect(url_for("index"))

        return render_template(
            "flow_preview.html",
            flow=flow,
            flow_tf=generate_flow_tf(flow),
            locals_snippet=generate_locals_snippet(flow),
            variables_snippet=generate_variables_snippet(flow),
            diagram_steps=_build_diagram_steps(flow),
        )

    @app.post("/flows/<flow_id>/delete")
    def delete_flow(flow_id: str) -> ResponseReturnValue:
        flow = store.get(flow_id)
        if flow is None:
            flash(f"Flow {flow_id} was not found.", "danger")
            return redirect(url_for("index"))
        if flow.readonly:
            flash("Read-only flows cannot be deleted.", "warning")
            return redirect(url_for("view_flow", flow_id=flow_id))
        store.delete(flow_id)
        flash(f"Deleted flow {flow_id}.", "success")
        return redirect(url_for("index"))

    @app.get("/flows/<flow_id>/download")
    def download_flow(flow_id: str) -> ResponseReturnValue:
        flow = _require_flow(flow_id)
        buffer = io.BytesIO(generate_flow_tf(flow).encode("utf-8"))
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"flow_{flow.flow_var_name}.tf",
            mimetype="text/plain",
        )

    @app.get("/flows/<flow_id>/download-package")
    def download_package(flow_id: str) -> ResponseReturnValue:
        flow = _require_flow(flow_id)
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"flow_{flow.flow_var_name}.tf", generate_flow_tf(flow))
            archive.writestr("locals_additions.tf", generate_locals_snippet(flow))
            archive.writestr("variables_additions.tf", generate_variables_snippet(flow))
        archive_buffer.seek(0)
        return send_file(
            archive_buffer,
            as_attachment=True,
            download_name=f"{flow.flow_var_name}_terraform_package.zip",
            mimetype="application/zip",
        )

    return app


app = create_app()


def _require_flow(flow_id: str) -> FlowDefinition:
    flow = store.get(flow_id)
    if flow is None:
        abort(404)
    return flow


def _default_form_data() -> dict[str, Any]:
    return {
        "flow_id": "",
        "source_system": "",
        "destination": "MPI",
        "health_board": "",
        "mllp_port": 2575,
        "hl7_version": "2.5",
        "sending_app": "",
        "validation_flow": "",
        "has_transformer": True,
        "transformer_image_name": "",
        "has_dedicated_sender": False,
        "destination_host": "",
        "destination_port": 2576,
        "enable_message_store": True,
    }


def _flow_to_form_data(flow: FlowDefinition) -> dict[str, Any]:
    return {
        "flow_id": flow.flow_id,
        "source_system": flow.source_system,
        "destination": flow.destination,
        "health_board": flow.health_board,
        "mllp_port": flow.mllp_port,
        "hl7_version": flow.hl7_version,
        "sending_app": flow.sending_app,
        "validation_flow": flow.validation_flow,
        "has_transformer": flow.has_transformer,
        "transformer_image_name": flow.transformer_image_name,
        "has_dedicated_sender": flow.has_dedicated_sender,
        "destination_host": flow.destination_host,
        "destination_port": flow.destination_port,
        "enable_message_store": flow.enable_message_store,
    }


def _flow_from_request(existing_flow_id: str | None = None) -> tuple[FlowDefinition | None, dict[str, Any]]:
    form_data: dict[str, Any] = {
        "flow_id": request.form.get("flow_id", "").strip().lower(),
        "source_system": request.form.get("source_system", "").strip().upper(),
        "destination": request.form.get("destination", "MPI").strip().upper() or "MPI",
        "health_board": request.form.get("health_board", "").strip().upper(),
        "mllp_port": request.form.get("mllp_port", "2575").strip(),
        "hl7_version": request.form.get("hl7_version", "").strip(),
        "sending_app": request.form.get("sending_app", "").strip(),
        "validation_flow": request.form.get("validation_flow", "").strip().lower(),
        "has_transformer": request.form.get("has_transformer") == "on",
        "transformer_image_name": request.form.get("transformer_image_name", "").strip(),
        "has_dedicated_sender": request.form.get("has_dedicated_sender") == "on",
        "destination_host": request.form.get("destination_host", "").strip(),
        "destination_port": request.form.get("destination_port", "2576").strip(),
        "enable_message_store": request.form.get("enable_message_store") == "on",
    }

    if not form_data["has_transformer"]:
        form_data["has_dedicated_sender"] = False
        form_data["transformer_image_name"] = ""

    errors: list[str] = []
    flow_id = str(form_data["flow_id"])
    if not FLOW_ID_PATTERN.fullmatch(flow_id):
        errors.append("Flow ID must be kebab-case, e.g. phw-to-mpi.")

    source_system = str(form_data["source_system"])
    if not source_system:
        errors.append("Source system is required.")

    if not str(form_data["health_board"]):
        errors.append("Health board is required.")

    if not str(form_data["hl7_version"]):
        errors.append("HL7 version is required.")

    if not str(form_data["sending_app"]):
        errors.append("Sending application is required.")

    if not str(form_data["validation_flow"]):
        errors.append("Validation flow is required.")

    if form_data["has_transformer"] and not str(form_data["transformer_image_name"]):
        errors.append("Transformer image name is required when a transformer is enabled.")

    requires_destination_host = (not form_data["has_transformer"]) or form_data["has_dedicated_sender"]
    if requires_destination_host and not str(form_data["destination_host"]):
        errors.append("Destination host is required for direct or dedicated sender patterns.")

    try:
        mllp_port = int(str(form_data["mllp_port"]))
        if not 1 <= mllp_port <= 65535:
            raise ValueError
    except ValueError:
        errors.append("MLLP port must be a valid port number.")
        mllp_port = 2575

    try:
        destination_port = int(str(form_data["destination_port"]))
        if not 1 <= destination_port <= 65535:
            raise ValueError
    except ValueError:
        errors.append("Destination port must be a valid port number.")
        destination_port = 2576

    existing = store.get(flow_id)
    if existing is not None and flow_id != existing_flow_id:
        errors.append(f"A flow with ID {flow_id} already exists.")

    if errors:
        for error in errors:
            flash(error, "danger")
        return None, form_data

    flow = FlowDefinition(
        flow_id=flow_id,
        source_system=source_system,
        mllp_port=mllp_port,
        hl7_version=str(form_data["hl7_version"]),
        sending_app=str(form_data["sending_app"]),
        validation_flow=str(form_data["validation_flow"]),
        health_board=str(form_data["health_board"]),
        destination=str(form_data["destination"]),
        has_transformer=bool(form_data["has_transformer"]),
        transformer_image_name=str(form_data["transformer_image_name"]),
        has_dedicated_sender=bool(form_data["has_dedicated_sender"]),
        destination_host=str(form_data["destination_host"]),
        destination_port=destination_port,
        enable_message_store=bool(form_data["enable_message_store"]),
        readonly=False,
    )
    return flow, _flow_to_form_data(flow)


def _generate_preview_files(flow: FlowDefinition | MpiOutboundFlowDefinition) -> dict[str, str]:
    if isinstance(flow, MpiOutboundFlowDefinition):
        return {
            "flow_tf": generate_subscription_flow_tf(flow),
            "locals_snippet": generate_subscription_locals_snippet(flow),
            "variables_snippet": generate_subscription_variables_snippet(flow),
        }
    return {
        "flow_tf": generate_flow_tf(flow),
        "locals_snippet": generate_locals_snippet(flow),
        "variables_snippet": generate_variables_snippet(flow),
    }


def _build_resource_summary(flow: FlowDefinition | MpiOutboundFlowDefinition) -> dict[str, Any]:
    """Return a plain-dict summary of resources that would be created for a flow."""
    fv = flow.flow_var_name
    if isinstance(flow, MpiOutboundFlowDefinition):
        container_apps = [f"hl7-server-{flow.source_slug.replace('_', '-')}"] + [
            f"hl7subsender-{sender.slug.replace('_', '-')}" for sender in flow.subscription_senders
        ]
        service_bus_subscriptions = [sender.health_board for sender in flow.subscription_senders]
        return {
            "container_apps": container_apps,
            "service_bus_queues": [],
            "service_bus_subscriptions": service_bus_subscriptions,
            "rbac_assignments": 1 + len(flow.subscription_senders),
            "pattern": flow.pattern,
            "has_transformer": False,
            "flow_var_name": fv,
        }

    container_apps: list[str] = [f"hl7-server-{flow.source_slug.replace('_', '-')}"]
    if flow.has_transformer:
        container_apps.append(f"hl7-{flow.source_slug.replace('_', '-')}-transformer")
    if flow.has_dedicated_sender:
        container_apps.append(f"hl7-sender-{flow.source_slug.replace('_', '-')}")

    service_bus_queues: list[str] = []
    if flow.has_transformer:
        service_bus_queues.append(f"pre-{flow.source_slug.replace('_', '-')}-transform")
    if flow.has_dedicated_sender:
        service_bus_queues.append(f"post-{flow.source_slug.replace('_', '-')}-transform")

    rbac_per_app = 2  # sender + receiver on its queue(s)
    rbac_assignments = len(container_apps) * rbac_per_app

    pattern = (
        "Direct (no transformer)"
        if not flow.has_transformer
        else ("Transform + Dedicated Sender" if flow.has_dedicated_sender else "Transform + Shared Sender")
    )

    return {
        "container_apps": container_apps,
        "service_bus_queues": service_bus_queues,
        "rbac_assignments": rbac_assignments,
        "pattern": pattern,
        "has_transformer": flow.has_transformer,
        "flow_var_name": fv,
    }


def _build_diagram_steps(flow: FlowDefinition) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = [
        {
            "title": "HL7 Server",
            "subtitle": f"MLLP {flow.mllp_port}",
            "icon": "bi-hdd-network",
            "tone": "primary",
        }
    ]

    if flow.has_transformer:
        steps.append(
            {
                "title": "Transformer Queue",
                "subtitle": f"{flow.source_slug}_transformer",
                "icon": "bi-stack",
                "tone": "info",
            }
        )
        steps.append(
            {
                "title": "HL7 Transformer",
                "subtitle": flow.transformer_image_name,
                "icon": "bi-shuffle",
                "tone": "warning",
            }
        )
        if flow.has_dedicated_sender:
            steps.append(
                {
                    "title": "Sender Queue",
                    "subtitle": f"{flow.source_slug}_sender",
                    "icon": "bi-stack",
                    "tone": "info",
                }
            )
            steps.append(
                {
                    "title": "Dedicated Sender",
                    "subtitle": f"{flow.destination_host}:{flow.destination_port}",
                    "icon": "bi-send",
                    "tone": "success",
                }
            )
        else:
            steps.append(
                {
                    "title": "Shared Sender Queue",
                    "subtitle": "sender",
                    "icon": "bi-stack",
                    "tone": "info",
                }
            )
    else:
        steps.append(
            {
                "title": "Shared Sender Queue",
                "subtitle": "sender",
                "icon": "bi-stack",
                "tone": "info",
            }
        )

    steps.append(
        {
            "title": flow.destination,
            "subtitle": flow.destination_host or "Shared MPI sender",
            "icon": "bi-bullseye",
            "tone": "dark",
        }
    )
    return steps
