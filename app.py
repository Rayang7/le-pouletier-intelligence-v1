import streamlit as st
import json
from datetime import date
from agent.backup import backup_json_text, restore_backup
from agent.db import init_db, connect
from agent import tools
from agent.orchestrator import ask_agent

st.set_page_config(page_title="Le Pouletier Intelligence", page_icon="🐔", layout="wide")
init_db()

st.title("🐔 Le Pouletier Intelligence")
st.caption("Noyau d'agent IA avicole — prototype cloud, priorité Burkina Faso.")
st.warning("Prototype : les données SQLite de l'hébergement gratuit peuvent être perdues lors d'un redéploiement. Ne l'utilise pas encore comme registre unique de production.")

with st.sidebar:
    st.subheader("État du système")
    st.write("Moteur IA : " + ("API Groq configurée" if st.secrets.get("GROQ_API_KEY", "") else "mode local limité"))
    st.caption("Les alertes sont calculées à l'ouverture et lors de l'actualisation. Ce prototype ne garantit pas une surveillance 24 h/24.")

tabs = st.tabs(["Assistant IA", "Production", "Stocks", "Finances", "Tâches et alertes", "Sauvegarde"])

with tabs[0]:
    st.subheader("Conversation avec l'agent")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    prompt = st.chat_input("Ex. : combien de poulets restent dans mes lots ?")
    if prompt:
        st.session_state.chat_history.append({"role":"user","content":prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Analyse en cours..."):
                answer = ask_agent(prompt, st.session_state.chat_history[:-1])
                st.markdown(answer)
        st.session_state.chat_history.append({"role":"assistant","content":answer})

with tabs[1]:
    st.subheader("Ajouter un lot")
    with st.form("flock_form"):
        name = st.text_input("Nom du lot")
        start_date = st.date_input("Date de mise en place", value=date.today())
        started = st.number_input("Effectif initial", min_value=1, value=100, step=10)
        dead = st.number_input("Mortalités", min_value=0, value=0, step=1)
        sold = st.number_input("Vendus", min_value=0, value=0, step=1)
        notes = st.text_input("Notes")
        submit = st.form_submit_button("Enregistrer le lot")
    if submit:
        try:
            result = tools.add_flock(name, start_date.isoformat(), started, dead, sold, notes)
            st.success(f"Lot enregistré. Effectif restant estimé : {result['birds_remaining']}.")
        except Exception as e:
            st.error(str(e))
    st.dataframe(tools.get_flock_data(), use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("Mouvement de stock")
    with st.form("stock_form"):
        item = st.text_input("Article")
        category = st.selectbox("Catégorie", ["Aliment", "Santé animale", "Emballage", "Carburant", "Autre"])
        unit = st.selectbox("Unité", ["kg", "sac", "unité", "litre", "boîte", "carton"])
        movement = st.selectbox("Mouvement", ["Entrée", "Sortie"])
        qty = st.number_input("Quantité", min_value=0.1, value=1.0)
        threshold = st.number_input("Seuil d'alerte", min_value=0.0, value=0.0)
        submit_stock = st.form_submit_button("Enregistrer le mouvement")
    if submit_stock:
        try:
            st.success(str(tools.add_stock_movement(item, category, qty, unit, threshold, movement)))
        except Exception as e:
            st.error(str(e))
    st.dataframe(tools.get_stock_status(), use_container_width=True, hide_index=True)

with tabs[3]:
    st.subheader("Synthèse financière")
    summary = tools.get_financial_summary()
    c1,c2,c3 = st.columns(3)
    c1.metric("Ventes", f"{summary['revenue_fcfa']:,.0f} FCFA")
    c2.metric("Dépenses", f"{summary['expenses_fcfa']:,.0f} FCFA")
    c3.metric("Solde simplifié", f"{summary['simple_balance_fcfa']:,.0f} FCFA")
    st.caption(summary["limitation"])
    with st.expander("Ajouter une dépense"):
        with st.form("expense_form"):
            d = st.date_input("Date", value=date.today())
            cat = st.selectbox("Catégorie", ["Aliments", "Poussins", "Santé animale", "Main-d'œuvre", "Énergie/eau", "Transport", "Autre"])
            amount = st.number_input("Montant FCFA", min_value=0.0, value=1000.0, step=500.0)
            note = st.text_input("Libellé")
            saved = st.form_submit_button("Enregistrer dépense")
        if saved:
            with connect() as con:
                con.execute("INSERT INTO expenses(date,category,amount,notes) VALUES(?,?,?,?)", (d.isoformat(),cat,float(amount),note))
            st.success("Dépense enregistrée.")
    with st.expander("Ajouter une vente"):
        with st.form("sale_form"):
            d2 = st.date_input("Date de vente", value=date.today(), key="sale_date")
            product = st.text_input("Produit vendu")
            qty2 = st.number_input("Quantité vendue", min_value=0.0, value=1.0)
            price = st.number_input("Prix unitaire FCFA", min_value=0.0, value=2500.0)
            customer = st.text_input("Client")
            saved2 = st.form_submit_button("Enregistrer vente")
        if saved2:
            if not product.strip():
                st.error("Précise le produit vendu.")
            else:
                with connect() as con:
                    con.execute("INSERT INTO sales(date,product,quantity,unit_price,customer) VALUES(?,?,?,?,?)", (d2.isoformat(),product.strip(),float(qty2),float(price),customer))
                st.success("Vente enregistrée.")

with tabs[4]:
    st.subheader("Tâches et alertes")
    with st.form("task_form"):
        due = st.date_input("Échéance", value=date.today())
        task = st.text_input("Tâche à effectuer")
        note = st.text_input("Détails", key="task_note")
        save = st.form_submit_button("Ajouter tâche")
    if save:
        try:
            st.success(str(tools.create_task(due.isoformat(), task, note)))
        except Exception as e:
            st.error(str(e))
    if st.button("Actualiser les alertes"):
        alerts = tools.check_alerts()
        if alerts:
            for alert in alerts:
                st.warning(alert["message"])
        else:
            st.success("Aucune tâche échue ou alerte de stock détectée.")
    st.write("Tâches à échéance :")
    st.dataframe(tools.get_due_tasks(), use_container_width=True, hide_index=True)

st.caption("Le Pouletier Intelligence — noyau initial. Valider les données et les recommandations avec des professionnels compétents pour les décisions sanitaires et réglementaires.")


with tabs[5]:
    st.subheader("Sauvegarde et restauration des données")
    st.warning("La sauvegarde est un fichier à conserver hors de Streamlit. La restauration remplace toutes les données actuelles de l'application par celles du fichier choisi.")
    st.markdown("### 1. Télécharger une sauvegarde")
    try:
        backup_text = backup_json_text()
        st.download_button(
            "Télécharger la sauvegarde JSON",
            data=backup_text,
            file_name=f"le-pouletier-sauvegarde-{date.today().isoformat()}.json",
            mime="application/json",
            help="Conserve ce fichier sur ton ordinateur ou dans un espace de stockage privé."
        )
    except Exception as exc:
        st.error(f"Impossible de créer la sauvegarde : {type(exc).__name__}")

    st.divider()
    st.markdown("### 2. Restaurer une sauvegarde existante")
    uploaded = st.file_uploader("Choisir un fichier JSON de sauvegarde", type=["json"], key="backup_upload")
    confirm_restore = st.checkbox("Je comprends que la restauration remplacera toutes les données actuellement enregistrées.")
    if st.button("Restaurer les données", type="secondary", disabled=(uploaded is None or not confirm_restore)):
        try:
            payload = json.loads(uploaded.getvalue().decode("utf-8"))
            counts = restore_backup(payload, confirmed=True)
            total = sum(counts.values())
            st.success(f"Restauration terminée : {total} enregistrement(s) importé(s).")
            st.json(counts)
        except Exception as exc:
            st.error(f"Restauration impossible : {type(exc).__name__}: {exc}")

    st.caption("Conseil : télécharge une sauvegarde après chaque session de saisie importante. Cette fonction réduit le risque de perte, mais ne remplace pas une base de données distante persistante.")
