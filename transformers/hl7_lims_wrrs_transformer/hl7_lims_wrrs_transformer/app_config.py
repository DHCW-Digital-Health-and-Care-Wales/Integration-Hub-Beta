"""Classification settings for the LIMS WRRS transformer, read directly from environment variables.

Kept inside this service (not in a shared library) so the MappingType values can be changed without
rebuilding other images. The values must stay in step with the Terraform subscription SQL filters
on the classified topic (``user.MappingType = '...'``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MAPPING_TYPE_NHS_ID_UPDATE = "LIMS_NHS_ID_UPDATE"
DEFAULT_MAPPING_TYPE_A40 = "ADT_A40"


@dataclass(frozen=True)
class MappingTypeConfig:
    nhs_id_update: str
    a40: str

    @staticmethod
    def read_env_config() -> "MappingTypeConfig":
        nhs_id_update = (os.getenv("MAPPING_TYPE_NHS_ID_UPDATE") or "").strip() or DEFAULT_MAPPING_TYPE_NHS_ID_UPDATE
        a40 = (os.getenv("MAPPING_TYPE_A40") or "").strip() or DEFAULT_MAPPING_TYPE_A40

        # Identical values would collapse two paths into one Service Bus message_id and lose a copy.
        if nhs_id_update == a40:
            raise ValueError(
                "MAPPING_TYPE_NHS_ID_UPDATE and MAPPING_TYPE_A40 must be different values, "
                f"both resolved to '{nhs_id_update}'"
            )

        return MappingTypeConfig(nhs_id_update=nhs_id_update, a40=a40)
