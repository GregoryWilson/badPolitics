import difflib

def unified(old:str,new:str, old_name="old", new_name="new"):
    return "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=old_name, tofile=new_name, lineterm=""))

def summary(old:str,new:str):
    sm=difflib.SequenceMatcher(None, old.splitlines(), new.splitlines())
    added=removed=changed=0
    for tag,i1,i2,j1,j2 in sm.get_opcodes():
        if tag=="insert": added += j2-j1
        elif tag=="delete": removed += i2-i1
        elif tag=="replace": changed += max(i2-i1,j2-j1)
    return {"added_lines":added,"removed_lines":removed,"changed_lines":changed,"similarity":round(sm.ratio(),4)}
