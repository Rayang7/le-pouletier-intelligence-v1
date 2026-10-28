import json
import os
from pathlib import Path
import requests

from . import tools

SYSTEM_PROMPT = (Path(__file__).with_name("system_prompt.md")).read_text(encoding="utf-8")

TOOL_SCHEMAS = [
    {"type":"function","function":{"name":"get_flock_data","description":"Lire les lots et leurs effectifs enregistrés.","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"calculate_mortality","description":"Calculer mortalité et effectif restant des lots. flock_id est facultatif.","parameters":{"type":"object","properties":{"flock_id":{"type":"integer"}},"additionalProperties":False}}},
    {"type":"function","function":{"name":"get_stock_status","description":"Consulter les stocks et seuils d'alerte.","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"get_financial_summary","description":"Résumé financier sur une période ISO YYYY-MM-DD facultative.","parameters":{"type":"object","properties":{"start_date":{"type":"string"},"end_date":{"type":"string"}},"additionalProperties":False}}},
    {"type":"function","function":{"name":"forecast_feed_needs","description":"Estimer la quantité d'aliment nécessaire à partir de paramètres fournis.","parameters":{"type":"object","properties":{"birds":{"type":"integer"},"grams_per_bird_per_day":{"type":"number"},"days":{"type":"integer"}},"required":["birds","grams_per_bird_per_day","days"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"calculate_batch_cost","description":"Calculer le coût d'une bande à partir des coûts fournis.","parameters":{"type":"object","properties":{"chicks_cost":{"type":"number"},"feed_cost":{"type":"number"},"health_cost":{"type":"number"},"labor_cost":{"type":"number"},"energy_cost":{"type":"number"},"other_cost":{"type":"number"},"birds_sold":{"type":"integer"}},"required":["chicks_cost","feed_cost"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"get_due_tasks","description":"Lister les tâches échues ou à échéance aujourd'hui.","parameters":{"type":"object","properties":{"today":{"type":"string"}},"additionalProperties":False}}}
]
ALLOWED_TOOLS = {
    "get_flock_data": tools.get_flock_data,
    "calculate_mortality": tools.calculate_mortality,
    "get_stock_status": tools.get_stock_status,
    "get_financial_summary": tools.get_financial_summary,
    "forecast_feed_needs": tools.forecast_feed_needs,
    "calculate_batch_cost": tools.calculate_batch_cost,
    "get_due_tasks": tools.get_due_tasks,
}

def local_answer(question):
    q = question.lower()
    if any(w in q for w in ("mortalité", "mortalite", "mort", "décès", "deces")):
        data = tools.calculate_mortality()
        if not data:
            return "Aucun lot enregistré. Ajoute d'abord un lot pour calculer la mortalité."
        lines = [f"- {x['name']} : {x['birds_dead']}/{x['birds_started']} morts ({x['mortality_percent']} %), {x['birds_remaining']} restants." for x in data]
        return "Suivi des mortalités enregistrées :\n" + "\n".join(lines) + "\nSi la mortalité est inhabituelle ou augmente rapidement, contacte un vétérinaire/technicien avicole."
    if any(w in q for w in ("stock", "provende", "aliment", "médicament", "medicament")):
        data = tools.get_stock_status()
        if not data:
            return "Aucun stock enregistré pour le moment."
        return "État des stocks :\n" + "\n".join(
            f"- {x['name']} : {x['quantity']} {x['unit']} (seuil {x['min_quantity']}; alerte : {'oui' if x['alert'] else 'non'})." for x in data)
    if any(w in q for w in ("finance", "dépense", "depense", "vente", "recette", "rentable", "bénéfice", "benefice")):
        x = tools.get_financial_summary()
        return (f"Période {x['start_date']} à {x['end_date']} : ventes {x['revenue_fcfa']:,.0f} FCFA; "
                f"dépenses {x['expenses_fcfa']:,.0f} FCFA; solde simplifié {x['simple_balance_fcfa']:,.0f} FCFA. "
                + x["limitation"])
    return ("Je peux consulter les lots, calculer les mortalités, vérifier les stocks, résumer les finances, estimer les besoins en aliments et lister les tâches échues. "
            "Pour une estimation, donne les paramètres nécessaires. Sans clé API IA, je fonctionne en mode local limité.")

def ask_agent(question, history=None):
    question = str(question).strip()
    if not question:
        return "Écris une question pour commencer."
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    try:
        import streamlit as st
        api_key = st.secrets.get("GROQ_API_KEY", api_key).strip()
    except Exception:
        pass
    if not api_key:
        return local_answer(question)

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    messages = [{"role":"system", "content":SYSTEM_PROMPT}]
    for item in (history or [])[-8:]:
        if item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
            messages.append({"role":item["role"], "content":item["content"]})
    messages.append({"role":"user", "content":question})
    try:
        for _ in range(4):
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization":f"Bearer {api_key}", "Content-Type":"application/json"},
                json={"model":model,"messages":messages,"tools":TOOL_SCHEMAS,"tool_choice":"auto","temperature":0.2,"max_tokens":900},
                timeout=35)
            response.raise_for_status()
            payload = response.json()
            message = payload["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return message.get("content") or "Je n'ai pas pu produire une réponse textuelle."
            messages.append(message)
            for call in tool_calls:
                name = call.get("function", {}).get("name", "")
                if name not in ALLOWED_TOOLS:
                    result = {"error":"Outil non autorisé."}
                else:
                    try:
                        args = json.loads(call["function"].get("arguments") or "{}")
                        result = ALLOWED_TOOLS[name](**args)
                    except Exception as exc:
                        result = {"error":f"Appel d'outil invalide : {type(exc).__name__}: {exc}"}
                messages.append({"role":"tool","tool_call_id":call["id"],"content":json.dumps(result,ensure_ascii=False,default=str)})
        return "J'ai atteint la limite d'étapes de cet échange. Reformule la demande en la divisant en deux questions."
            except Exception:
        return local_answer(question) + "\n\nLe service IA distant est indisponible; réponse locale de secours utilisée."
            )
