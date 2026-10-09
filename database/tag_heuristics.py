import re
from typing import Dict, List, Any

def has_keyword(text: str, keywords: List[str]) -> bool:
    if not text:
        return False
    text = text.lower()
    for kw in keywords:
        if kw in text:
            return True
    return False

def classify_item(item_data: Dict[str, Any]) -> List[str]:
    """
    Classifica automaticamente un oggetto in base alle sue proprietà meccaniche 
    da Showdown e al testo descrittivo.
    Restituisce una lista di tag generici (offensive, defensive, disruptive, unclassified).
    """
    tags = set()
    
    desc = item_data.get("desc", "") + " " + item_data.get("shortDesc", "")
    desc = desc.lower()

    # Offensive heuristics
    boosts = item_data.get("boosts", {})
    if "atk" in boosts or "spa" in boosts:
        tags.add("offensive")
    
    if item_data.get("isGem"):
        tags.add("offensive")
        
    if item_data.get("isChoice") and not has_keyword(desc, ["speed"]):
        tags.add("offensive")

    if any(k in item_data for k in ["onBasePowerPriority", "onModifyAtkPriority", "onModifySpAPriority"]):
        tags.add("offensive")
        
    if has_keyword(desc, ["1.2x power", "1.3x power", "1.5x power", "power multiplied by", "attack is raised", "sp. atk is raised"]):
        tags.add("offensive")

    # Defensive heuristics
    if "def" in boosts or "spd" in boosts:
        tags.add("defensive")

    if any(k in item_data for k in ["onModifyDefPriority", "onModifySpDPriority", "onDamagePriority", "onSourceModifyAtkPriority", "onSourceModifySpAPriority", "onTryHealPriority"]):
        tags.add("defensive")

    if has_keyword(desc, ["restores", "heals", "survive an attack", "immune to", "takes 1/2", "receives 1/2", "halves damage", "reduces damage", "defense is raised", "sp. def is raised"]):
        tags.add("defensive")
        
    if "onResidualOrder" in item_data and has_keyword(desc, ["restores"]):
        tags.add("defensive")

    # Disruptive heuristics
    if any(k in item_data for k in ["onAfterMoveSecondaryPriority"]):
        tags.add("disruptive")

    if has_keyword(desc, ["switches out", "forces", "lowers", "steals", "disables", "infatuated", "poisons", "paralyzes", "sleep"]):
        # "lowers" could mean lowers user stats (e.g. choice specs with superpower? no, item desc usually explains the item effect).
        if not has_keyword(desc, ["lowers the holder's", "lowers its"]):
            tags.add("disruptive")
            
    if has_keyword(desc, ["damage to attacker", "loses hp"]):
        tags.add("disruptive") # E.g. Rocky Helmet, Sticky Barb

    if not tags:
        tags.add("unclassified")
        
    return list(tags)


def classify_ability(ability_data: Dict[str, Any]) -> List[str]:
    """
    Classifica automaticamente un'abilità in base alle sue proprietà meccaniche 
    da Showdown e al testo descrittivo.
    Restituisce una lista di tag generici (offensive, defensive, disruptive, unclassified).
    """
    tags = set()
    
    desc = ability_data.get("desc", "") + " " + ability_data.get("shortDesc", "")
    desc = desc.lower()

    # Offensive heuristics
    if any(k in ability_data for k in ["onBasePowerPriority", "onModifyAtkPriority", "onModifySpAPriority", "onAllyBasePowerPriority"]):
        tags.add("offensive")

    if has_keyword(desc, ["attack is raised", "sp. atk is raised", "highest stat is raised", "power multiplied by", "1.2x power", "1.3x power", "1.5x power", "attack is doubled"]):
        tags.add("offensive")

    # Defensive heuristics
    if any(k in ability_data for k in ["onModifyDefPriority", "onModifySpDPriority", "onDamagePriority", "onSourceModifyAtkPriority", "onSourceModifySpAPriority", "onTryHealPriority"]):
        tags.add("defensive")

    # Some abilities use flags or specific text for immunity
    flags = ability_data.get("flags", {})
    if "breakable" in flags:
        # Most breakable abilities are defensive (Levitate, Filter, Magic Bounce)
        tags.add("defensive")

    if has_keyword(desc, ["immune to", "restores", "receives 1/2", "takes 1/2", "receives 3/4", "cannot be poisoned", "cannot be paralyzed", "cannot fall asleep", "cannot be burned", "cannot be frozen", "defense is raised", "sp. def is raised", "prevents other pokemon from lowering"]):
        tags.add("defensive")

    # Disruptive heuristics
    if any(k in ability_data for k in ["onDamagingHitOrder"]):
        # E.g. Iron Barbs, Rough Skin, Effect Spore, Static
        tags.add("disruptive")
        # Contact damage can also be seen as defensive deterrence, but disruptive is a good fit.
        tags.add("defensive")

    if "onAnySwitchInPriority" in ability_data and has_keyword(desc, ["lowers"]):
        tags.add("disruptive") # E.g. Intimidate

    if has_keyword(desc, ["lowers the attack", "lowers the sp. atk", "lowers the speed", "lowers the defense", "lowers the sp. def"]):
        tags.add("disruptive")

    if has_keyword(desc, ["poisoned, paralyzed, or fall asleep", "infatuated", "disabled", "burned", "paralyzed", "poisoned"]):
        if not has_keyword(desc, ["this pokemon cannot be", "cures it", "ignores burn"]): 
            tags.add("disruptive")

    if not tags:
        tags.add("unclassified")
        
    return list(tags)
