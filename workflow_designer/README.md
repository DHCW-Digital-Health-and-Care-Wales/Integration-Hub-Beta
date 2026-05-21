# Workflow Designer

Workflow Designer is a standalone Flask web application for generating Integration Hub Terraform flow files.

## Features

- Create new HL7 integration flow definitions from a web form
- Preview the generated Terraform before download
- Export `flow_<name>.tf`, `locals_additions.tf`, and `variables_additions.tf`
- Seeded with existing NHS Wales Integration Hub flow examples as read-only references

## Local development

```bash
uv sync
uv run flask --app workflow_designer.app run --port 5001
```

## Quality checks

```bash
bash check.sh
```

## Generated outputs

For each flow the app produces:

- `flow_<flow_id_underscored>.tf`
- `locals_additions.tf`
- `variables_additions.tf`

The generated Terraform assumes the target Terraform repository already defines the shared sender queue and optional message store queue locals/IDs used by existing Integration Hub flows.
