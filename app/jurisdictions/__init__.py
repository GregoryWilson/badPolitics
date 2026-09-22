from app.jurisdictions.registry import register_adapter, get_adapter, list_adapters
from app.jurisdictions.federal import FederalCongressAdapter
from app.jurisdictions.texas import TexasTLOAdapter

register_adapter(FederalCongressAdapter())
register_adapter(TexasTLOAdapter())

__all__=["get_adapter","list_adapters"]
