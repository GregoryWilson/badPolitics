from app.jurisdictions.base import JurisdictionAdapter

_ADAPTERS: dict[str,JurisdictionAdapter]={}

def register_adapter(adapter:JurisdictionAdapter):
    _ADAPTERS[adapter.code.upper()]=adapter
    return adapter

def get_adapter(code:str) -> JurisdictionAdapter:
    adapter=_ADAPTERS.get(code.upper())
    if not adapter:
        raise ValueError(f"Unsupported jurisdiction: {code}")
    return adapter

def list_adapters():
    return [{
        "code":adapter.code,
        "name":adapter.name,
        "source_system":adapter.source_system,
        "source_info":adapter.source_info(),
    } for adapter in _ADAPTERS.values()]
