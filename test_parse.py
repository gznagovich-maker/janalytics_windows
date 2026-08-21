import re
import json

def js_to_dict(js_str):
    start = js_str.find('{')
    end = js_str.rfind('}')
    obj_str = js_str[start:end+1]
    
    # 1. Quota le chiavi non quotate (es. name: -> "name":)
    # Aggiungiamo anche il supporto per le doppie virgolette esistenti se ci sono
    obj_str = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)\s*:', r'\1"\2":', obj_str)
    
    # Rimuovi virgole trailing
    obj_str = re.sub(r',\s*}', '}', obj_str)
    obj_str = re.sub(r',\s*\]', ']', obj_str)
    
    try:
        return json.loads(obj_str)
    except Exception as e:
        print('JSON decode error:', e)
        # return dict()

if __name__ == "__main__":
    text = open('items.js', encoding='utf-8').read()
    d = js_to_dict(text)
    if d: print('Items parsed:', len(d))
