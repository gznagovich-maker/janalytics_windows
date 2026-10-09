import re, json
s = open("items.js", encoding="utf-8").read()
start = s.find("{")
end = s.rfind("}")
obj_str = s[start:end+1]
obj_str = re.sub(r"([{,]\s*)([a-zA-Z0-9_]+)\s*:", r"\1\"\2\":", obj_str)
obj_str = re.sub(r",\s*}", "}", obj_str)
obj_str = re.sub(r",\s*\]", "]", obj_str)
d = json.loads(obj_str)
print("Eviolite:", d.get("eviolite"))
print("Choice Band:", d.get("choiceband"))
print("Leftovers:", d.get("leftovers"))
print("Intimidate (from abilities):", json.loads(re.sub(r",\s*\]", "]", re.sub(r",\s*}", "}", re.sub(r"([{,]\s*)([a-zA-Z0-9_]+)\s*:", r"\1\"\2\":", open("abilities.js", encoding="utf-8").read()[open("abilities.js", encoding="utf-8").read().find("{"):open("abilities.js", encoding="utf-8").read().rfind("}")+1])))).get("intimidate"))

