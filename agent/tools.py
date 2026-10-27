from datetime import date, datetime
from .db import connect

def _rows(query, params=()):
    with connect() as con:
        return [dict(r) for r in con.execute(query, params).fetchall()]

def get_flock_data():
    return _rows("SELECT id,name,start_date,birds_started,birds_dead,birds_sold,notes FROM flocks ORDER BY start_date DESC,id DESC")

def calculate_mortality(flock_id=None):
    if flock_id is None:
        flocks = get_flock_data()
    else:
        flocks = _rows("SELECT id,name,start_date,birds_started,birds_dead,birds_sold,notes FROM flocks WHERE id=?", (int(flock_id),))
    results = []
    for f in flocks:
        start = int(f["birds_started"])
        dead = int(f["birds_dead"])
        results.append({
            "id": f["id"], "name": f["name"], "birds_started": start,
            "birds_dead": dead, "mortality_percent": round(dead / start * 100, 2) if start else 0,
            "birds_remaining": start - dead - int(f["birds_sold"])
        })
    return results

def get_stock_status():
    items = _rows("SELECT name,category,quantity,unit,min_quantity,updated_at FROM stock ORDER BY name")
    for item in items:
        item["alert"] = float(item["quantity"]) <= float(item["min_quantity"])
    return items

def get_financial_summary(start_date=None, end_date=None):
    start_date = start_date or date.today().replace(day=1).isoformat()
    end_date = end_date or date.today().isoformat()
    with connect() as con:
        revenue = con.execute(
            "SELECT COALESCE(SUM(quantity*unit_price),0) FROM sales WHERE date BETWEEN ? AND ?",
            (start_date, end_date)).fetchone()[0]
        expenses = con.execute(
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE date BETWEEN ? AND ?",
            (start_date, end_date)).fetchone()[0]
    return {
        "start_date": start_date, "end_date": end_date,
        "revenue_fcfa": round(float(revenue), 2),
        "expenses_fcfa": round(float(expenses), 2),
        "simple_balance_fcfa": round(float(revenue) - float(expenses), 2),
        "limitation": "Solde simplifié des ventes moins dépenses enregistrées; ce n'est pas un bénéfice comptable complet."
    }

def forecast_feed_needs(birds, grams_per_bird_per_day, days):
    birds, grams_per_bird_per_day, days = int(birds), float(grams_per_bird_per_day), int(days)
    if birds < 0 or grams_per_bird_per_day < 0 or days < 0:
        raise ValueError("Les effectifs, rations et durées doivent être positifs ou nuls.")
    kg = birds * grams_per_bird_per_day * days / 1000
    return {"birds": birds, "grams_per_bird_per_day": grams_per_bird_per_day,
            "days": days, "feed_kg": round(kg, 2),
            "note": "Estimation fondée sur la ration saisie; la ration réelle dépend de l'âge, de la souche et des conditions d'élevage."}

def calculate_batch_cost(chicks_cost, feed_cost, health_cost=0, labor_cost=0, energy_cost=0, other_cost=0, birds_sold=0):
    costs = [float(chicks_cost), float(feed_cost), float(health_cost), float(labor_cost), float(energy_cost), float(other_cost)]
    if any(x < 0 for x in costs) or int(birds_sold) < 0:
        raise ValueError("Les coûts et quantités doivent être positifs ou nuls.")
    total = round(sum(costs), 2)
    sold = int(birds_sold)
    return {"total_cost_fcfa": total, "birds_sold": sold,
            "cost_per_bird_sold_fcfa": round(total / sold, 2) if sold else None,
            "note": "Le coût unitaire est calculé par poulet vendu; vérifier que tous les coûts pertinents sont inclus."}

def create_task(due_date, task, notes=""):
    # Validate ISO date to avoid storing malformed deadlines.
    datetime.strptime(str(due_date), "%Y-%m-%d")
    task = str(task).strip()
    if not task:
        raise ValueError("La tâche ne peut pas être vide.")
    with connect() as con:
        cur = con.execute(
            "INSERT INTO tasks(due_date,task,status,notes) VALUES(?,?,?,?)",
            (str(due_date), task, "À faire", str(notes)))
        return {"id": cur.lastrowid, "due_date": str(due_date), "task": task, "status": "À faire"}

def get_due_tasks(today=None):
    today = today or date.today().isoformat()
    return _rows("SELECT id,due_date,task,status,notes FROM tasks WHERE status='À faire' AND due_date<=? ORDER BY due_date,id", (today,))

def add_flock(name, start_date, birds_started, birds_dead=0, birds_sold=0, notes=""):
    datetime.strptime(str(start_date), "%Y-%m-%d")
    name = str(name).strip()
    birds_started, birds_dead, birds_sold = int(birds_started), int(birds_dead), int(birds_sold)
    if not name:
        raise ValueError("Le nom du lot est obligatoire.")
    if birds_started <= 0 or birds_dead < 0 or birds_sold < 0 or birds_dead + birds_sold > birds_started:
        raise ValueError("Effectifs incohérents : départ > 0 et mortalités + ventes <= effectif initial.")
    with connect() as con:
        cur = con.execute(
            "INSERT INTO flocks(name,start_date,birds_started,birds_dead,birds_sold,notes) VALUES(?,?,?,?,?,?)",
            (name, str(start_date), birds_started, birds_dead, birds_sold, str(notes)))
        return {"id": cur.lastrowid, "name": name, "birds_remaining": birds_started-birds_dead-birds_sold}

def add_stock_movement(name, category, quantity, unit, min_quantity=0, movement="Entrée"):
    name = str(name).strip()
    quantity, min_quantity = float(quantity), float(min_quantity)
    if not name or quantity <= 0 or min_quantity < 0:
        raise ValueError("Article obligatoire; quantité strictement positive et seuil positif ou nul.")
    if movement not in ("Entrée", "Sortie"):
        raise ValueError("Le mouvement doit être 'Entrée' ou 'Sortie'.")
    with connect() as con:
        existing = con.execute("SELECT quantity,unit FROM stock WHERE name=?", (name,)).fetchone()
        if existing and existing["unit"] != unit:
            raise ValueError(f"Unité incohérente : cet article est déjà suivi en {existing['unit']}.")
        current = float(existing["quantity"]) if existing else 0.0
        new_qty = current + quantity if movement == "Entrée" else current - quantity
        if new_qty < -1e-9:
            raise ValueError("Stock insuffisant pour cette sortie.")
        if existing:
            con.execute("UPDATE stock SET category=?,quantity=?,min_quantity=?,updated_at=? WHERE name=?",
                        (category, new_qty, min_quantity, date.today().isoformat(), name))
        else:
            if movement == "Sortie":
                raise ValueError("Impossible de sortir un article qui n'existe pas encore en stock.")
            con.execute("INSERT INTO stock(name,category,quantity,unit,min_quantity,updated_at) VALUES(?,?,?,?,?,?)",
                        (name, category, new_qty, unit, min_quantity, date.today().isoformat()))
    return {"name": name, "movement": movement, "quantity_after": round(new_qty, 3), "unit": unit}

def log_event(event_type, severity, message):
    if severity not in ("info", "warning", "critical"):
        raise ValueError("Sévérité invalide.")
    with connect() as con:
        con.execute("INSERT INTO agent_events(event_type,severity,message) VALUES(?,?,?)",
                    (str(event_type), severity, str(message)))

def check_alerts(today=None):
    today = today or date.today().isoformat()
    alerts = []
    for item in get_stock_status():
        if item["alert"]:
            alerts.append({"type": "stock", "severity": "warning",
                           "message": f"Stock bas : {item['name']} = {item['quantity']} {item['unit']} (seuil {item['min_quantity']} {item['unit']})."})
    for task in get_due_tasks(today):
        alerts.append({"type": "task", "severity": "warning",
                       "message": f"Tâche échue/à échéance : {task['task']} (échéance {task['due_date']})."})
    for alert in alerts:
        log_event(alert["type"], alert["severity"], alert["message"])
    return alerts
