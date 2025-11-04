def derive_vendor(model_number: str) -> str:
    """
    Derive vendor from model number prefix.
    ST→Seagate, WD→Western Digital, DT/MG→Toshiba, HUA/HUS→Hitachi, IBM→IBM, else Unknown
    """
    if not model_number:
        return 'Unknown'
    
    model_upper = model_number.upper().strip()
    
    if model_upper.startswith('ST'):
        return 'Seagate'
    elif model_upper.startswith('WD'):
        return 'Western Digital'
    elif model_upper.startswith(('DT', 'MG')):
        return 'Toshiba'
    elif model_upper.startswith(('HUA', 'HUS')):
        return 'Hitachi'
    elif model_upper.startswith('IBM'):
        return 'IBM'
    else:
        return 'Unknown'
