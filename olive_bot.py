import os, io, logging, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8692793914:AAFEMavMFva4Eyj1uJzPqaA7xX_8MreHjaw")

# ── WEB SERVER ──────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, *a): pass
threading.Thread(target=lambda: HTTPServer(("0.0.0.0", 8080), H).serve_forever(), daemon=True).start()

# ── MACHINES DATA ───────────────────────────────────────
MACHINES = {
    "SPA 130": 9000,
    "SPA 140": 10000,
}
BATTERIES = {
    "AP 200 (2500 DH)": 2500,
    "AP 300 (4000 DH)": 4000,
    "AP 500 (5000 DH)": 5000,
    "AR 3000 (22500 DH)": 22500,
}
CHARGEURS = {
    "AL 301 (1690 DH)": 1690,
    "AL 501 (2090 DH)": 2090,
}
ACCESSOIRES = {
    "Harnais AR L + câble (4000 DH)": 4000,
    "Pochette AP (1790 DH)": 1790,
    "Sans accessoires": 0,
}

SKIP = "⏭ Passer"
G1 = HexColor("#1E5B3A"); G2 = HexColor("#2E7D52"); OR = HexColor("#D4500A")
INK = HexColor("#1A1A1A"); GRY = HexColor("#888888"); PAL = HexColor("#F4F0E8")
RUL = HexColor("#DDDDDD"); WRM = HexColor("#FAF8F4"); RED = HexColor("#E74C3C")
GLD = HexColor("#C8860A")

# ── STATES ──────────────────────────────────────────────
(S_ECART_ARBRE, S_ECART_LIGNE, S_SUPERFICIE, S_RENDEMENT,
 S_DUR_MANUEL, S_DUR_MACHINE, S_NB_OUV, S_COUT_OUV,
 S_DUREE_CAMP, S_MACHINE, S_BATTERIE, S_CHARGEUR, S_ACCESS) = range(13)

# ── CALCUL ──────────────────────────────────────────────
def calculer(d):
    # Plantation
    ecart_a = d["ecart_arbre"]
    ecart_l = d["ecart_ligne"]
    arbres_ha = 10000 / (ecart_a * ecart_l)
    superficie = d["superficie"]
    total_arbres = arbres_ha * superficie
    rendement = d["rendement"]  # kg/arbre

    # Production
    prod_ha = arbres_ha * rendement  # kg/ha
    prod_ferme = total_arbres * rendement  # kg total

    # Durées
    dur_manuel = d["dur_manuel"]   # min/arbre
    dur_machine = d["dur_machine"]  # min/arbre
    h_jour = 8  # heures/jour
    min_jour = h_jour * 60

    # Productivité
    arbres_j_manuel = min_jour / dur_manuel
    arbres_j_machine = min_jour / dur_machine

    prod_j_manuel = arbres_j_manuel * rendement   # kg/jour/ouvrier
    prod_j_machine = arbres_j_machine * rendement  # kg/jour/machine

    # Équipes
    duree_camp = d["duree_camp"]  # jours objectif
    nb_ouvriers = d["nb_ouvriers"]  # par machine

    # Jours pour finir 1 ha
    jours_ha_manuel = (arbres_ha * dur_manuel) / (min_jour)
    jours_ha_machine = (arbres_ha * dur_machine) / (min_jour)

    # Jours pour finir la ferme (avec 1 équipe)
    jours_ferme_manuel = total_arbres * dur_manuel / min_jour
    jours_ferme_machine = total_arbres * dur_machine / min_jour

    # Équipes nécessaires pour finir en duree_camp jours
    equipes_manuel = max(1, round(jours_ferme_manuel / duree_camp + 0.5))
    equipes_machine = max(1, round(jours_ferme_machine / duree_camp + 0.5))

    # Coûts
    cout_ouvrier = d["cout_ouvrier"]  # DH/jour
    # Manuel : ouvriers par caisse (25kg)
    cout_manuel_kg = cout_ouvrier / prod_j_manuel  # DH/kg
    cout_manuel_ha = cout_manuel_kg * prod_ha
    cout_manuel_ferme = cout_manuel_kg * prod_ferme

    # Machine : nb_ouvriers opérateurs
    cout_ops_jour = cout_ouvrier * nb_ouvriers
    cout_ops_kg = cout_ops_jour / prod_j_machine
    cout_machine_ha = cout_ops_kg * prod_ha
    cout_machine_ferme = cout_ops_kg * prod_ferme

    # Investissement
    prix_machine = d.get("prix_machine", 0)
    prix_batterie = d.get("prix_batterie", 0)
    prix_chargeur = d.get("prix_chargeur", 0)
    prix_access = d.get("prix_access", 0)
    investissement = prix_machine + prix_batterie + prix_chargeur + prix_access

    # Économie
    economie_ha = cout_manuel_ha - cout_machine_ha
    economie_ferme = cout_manuel_ferme - cout_machine_ferme
    economie_kg = cout_manuel_kg - cout_ops_kg

    # Payback (combien de saisons pour récupérer l'investissement)
    payback = (investissement / economie_ferme) if economie_ferme > 0 else None

    # Gain de temps
    gain_jours_ha = jours_ha_manuel - jours_ha_machine
    gain_jours_ferme = jours_ferme_manuel - jours_ferme_machine
    gain_pct = (gain_jours_ferme / jours_ferme_manuel * 100) if jours_ferme_manuel > 0 else 0

    return {
        "arbres_ha": round(arbres_ha, 1),
        "total_arbres": round(total_arbres, 0),
        "prod_ha": round(prod_ha, 0),
        "prod_ferme_t": round(prod_ferme / 1000, 2),
        "prod_ferme_kg": round(prod_ferme, 0),
        "arbres_j_manuel": round(arbres_j_manuel, 1),
        "arbres_j_machine": round(arbres_j_machine, 1),
        "prod_j_manuel": round(prod_j_manuel, 0),
        "prod_j_machine": round(prod_j_machine, 0),
        "jours_ha_manuel": round(jours_ha_manuel, 1),
        "jours_ha_machine": round(jours_ha_machine, 1),
        "jours_ferme_manuel": round(jours_ferme_manuel, 0),
        "jours_ferme_machine": round(jours_ferme_machine, 0),
        "equipes_manuel": equipes_manuel,
        "equipes_machine": equipes_machine,
        "cout_manuel_kg": round(cout_manuel_kg, 2),
        "cout_machine_kg": round(cout_ops_kg, 2),
        "cout_manuel_ha": round(cout_manuel_ha, 0),
        "cout_machine_ha": round(cout_machine_ha, 0),
        "cout_manuel_ferme": round(cout_manuel_ferme, 0),
        "cout_machine_ferme": round(cout_machine_ferme, 0),
        "investissement": investissement,
        "economie_ha": round(economie_ha, 0),
        "economie_ferme": round(economie_ferme, 0),
        "economie_kg": round(economie_kg, 3),
        "payback": round(payback, 1) if payback else None,
        "gain_jours_ha": round(gain_jours_ha, 1),
        "gain_jours_ferme": round(gain_jours_ferme, 0),
        "gain_pct": round(gain_pct, 0),
    }

def format_result(d, r):
    ml = d.get("machine_label", "SPA")
    dc = d["duree_camp"]
    lines = [
        "Duree/arbre",
        "Arbres/j/equipe",
        "Production/j kg",
        "Jours/ha",
        "Jours ferme 1eq",
        f"Equipes obj{dc}j",
        "---",
        "Cout/kg DH",
        "Cout/ha DH",
        "Cout ferme DH",
    ]
    vals_m = [
        f"{d['dur_manuel']}min",
        str(r['arbres_j_manuel']),
        str(r['prod_j_manuel']),
        str(r['jours_ha_manuel']),
        f"{r['jours_ferme_manuel']:.0f}",
        str(r['equipes_manuel']),
        "---",
        str(r['cout_manuel_kg']),
        str(r['cout_manuel_ha']),
        str(r['cout_manuel_ferme']),
    ]
    vals_mc = [
        f"{d['dur_machine']}min",
        str(r['arbres_j_machine']),
        str(r['prod_j_machine']),
        str(r['jours_ha_machine']),
        f"{r['jours_ferme_machine']:.0f}",
        str(r['equipes_machine']),
        "---",
        str(r['cout_machine_kg']),
        str(r['cout_machine_ha']),
        str(r['cout_machine_ferme']),
    ]
    rows = [f"{'':20} {'Manuel':>8} {ml:>8}"]
    rows.append("-"*38)
    for l, m, mc in zip(lines, vals_m, vals_mc):
        if l == "---":
            rows.append("-"*38)
        else:
            rows.append(f"{l:<20} {m:>8} {mc:>8}")
    table = "\n".join(rows)

    txt = "\U0001fad2 *SIMULATION RECOLTE OLIVES - STIHL*\n"
    txt += f"Ecartement: {d['ecart_arbre']}m x {d['ecart_ligne']}m\n"
    txt += f"Arbres/ha: *{r['arbres_ha']}* | Total: *{r['total_arbres']:.0f}*\n"
    txt += f"Production: *{r['prod_ferme_t']} tonnes*\n\n"
    txt += "*COMPARATIF TERRAIN*\n"
    txt += "```\n" + table + "\n```\n\n"
    txt += "*KPI DECISION*\n"
    txt += f"Gain temps: *{r['gain_jours_ferme']:.0f} jours* ({r['gain_pct']:.0f}%)\n"
    txt += f"Economie/ha: *{r['economie_ha']:,} DH*\n"
    txt += f"Economie totale: *{r['economie_ferme']:,} DH*\n"
    txt += f"Economie/kg: *{r['economie_kg']} DH*\n"
    if r["investissement"] > 0:
        txt += f"Investissement: *{r['investissement']:,} DH*\n"
    if r["payback"]:
        txt += f"Payback: *{r['payback']} saisons*\n"
    txt += "\n_/simulation pour recommencer_"
    return txt


# ── PDF ──────────────────────────────────────────────────
_n = [0]
def S(size=9, color=INK, bold=False, italic=False, align=TA_LEFT, leading=None):
    _n[0] += 1
    fn = "Helvetica-Bold" if bold else ("Helvetica-Oblique" if italic else "Helvetica")
    return ParagraphStyle(f"s{_n[0]}", fontName=fn, fontSize=size, textColor=color,
        leading=leading or max(10, int(size * 1.5)), alignment=align)
def P(t, **k): return Paragraph(str(t or "—"), S(**k))
def SP(h=3): return Spacer(1, h * mm)
def T(rows, widths, ex=None):
    t = Table(rows, colWidths=[w * mm for w in widths])
    base = [("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
            ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE")]
    t.setStyle(TableStyle(base + (ex or []))); return t

def generate_pdf(d, r):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=16*mm, rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm)
    story = []
    machine_label = d.get("machine_label", "SPA")

    # Cover
    story.append(T([[
        P("STIHL", size=10, color=HexColor("#AADDBB"), bold=True),
        P("Simulation Récolte Olives\nComparatif Machine vs Manuel", size=14,
          color=white, bold=True, align=TA_CENTER, leading=18),
        P("", size=9),
    ]], [20, 126, 20], [
        ("BACKGROUND",(0,0),(-1,-1),G1),
        ("TOPPADDING",(0,0),(-1,-1),8*mm),("BOTTOMPADDING",(0,0),(-1,-1),8*mm),
    ]))
    story.append(SP(4))

    # Paramètres
    story.append(P("① PARAMÈTRES DE LA FERME", size=11, bold=True, color=G1))
    story.append(SP(2))
    params = [
        [P("Superficie", size=9, bold=True), P(f"{d['superficie']} ha", size=9),
         P("Écartement", size=9, bold=True), P(f"{d['ecart_arbre']}m × {d['ecart_ligne']}m", size=9)],
        [P("Arbres / ha", size=9, bold=True), P(f"{r['arbres_ha']}", size=9),
         P("Total arbres", size=9, bold=True), P(f"{r['total_arbres']:.0f}", size=9)],
        [P("Rendement / arbre", size=9, bold=True), P(f"{d['rendement']} kg", size=9),
         P("Production ferme", size=9, bold=True), P(f"{r['prod_ferme_t']} tonnes", size=9, color=G1)],
        [P("Durée objectif campagne", size=9, bold=True), P(f"{d['duree_camp']} jours", size=9),
         P("Machine utilisée", size=9, bold=True), P(machine_label, size=9, color=G1)],
    ]
    pt = Table(params, colWidths=[44*mm, 38*mm, 44*mm, 40*mm])
    pt.setStyle(TableStyle([
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[WRM, PAL]),
        ("LINEBELOW",(0,0),(-1,-1),0.3,RUL),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
    ]))
    story.append(pt)
    story.append(SP(5))

    # Comparatif
    story.append(P("② COMPARATIF MANUEL vs MACHINE", size=11, bold=True, color=G1))
    story.append(SP(2))
    hdr = ["Indicateur", "Manuel", machine_label, "Avantage Machine"]
    comp = [
        [P(h, size=8, color=white, bold=True, align=TA_CENTER) for h in hdr],
        [P("Durée par arbre"),P(f"{d['dur_manuel']} min",align=TA_CENTER),P(f"{d['dur_machine']} min",align=TA_CENTER),P(f"{d['dur_manuel']-d['dur_machine']} min gagnées",color=G2,align=TA_CENTER)],
        [P("Arbres / jour / équipe"),P(f"{r['arbres_j_manuel']}",align=TA_CENTER),P(f"{r['arbres_j_machine']}",align=TA_CENTER),P(f"×{round(r['arbres_j_machine']/r['arbres_j_manuel'],1)} plus rapide",color=G2,align=TA_CENTER)],
        [P("Production / jour (kg)"),P(f"{r['prod_j_manuel']} kg",align=TA_CENTER),P(f"{r['prod_j_machine']} kg",align=TA_CENTER),P(f"+{r['prod_j_machine']-r['prod_j_manuel']} kg/j",color=G2,align=TA_CENTER)],
        [P("Jours pour 1 ha"),P(f"{r['jours_ha_manuel']} j",align=TA_CENTER),P(f"{r['jours_ha_machine']} j",align=TA_CENTER),P(f"{r['gain_jours_ha']} j gagnés",color=G2,align=TA_CENTER)],
        [P("Jours ferme (1 équipe)"),P(f"{r['jours_ferme_manuel']:.0f} j",align=TA_CENTER),P(f"{r['jours_ferme_machine']:.0f} j",align=TA_CENTER),P(f"{r['gain_jours_ferme']:.0f} j gagnés ({r['gain_pct']:.0f}%)",color=G2,align=TA_CENTER)],
        [P(f"Équipes pour {d['duree_camp']} jours"),P(f"{r['equipes_manuel']} équipes",align=TA_CENTER),P(f"{r['equipes_machine']} machines",align=TA_CENTER),P(f"{r['equipes_manuel']-r['equipes_machine']} équipes économisées",color=G2,align=TA_CENTER)],
    ]
    def ps9c(t, c=INK): return P(t, size=9, color=c, align=TA_CENTER)
    ct = Table(comp, colWidths=[52*mm, 34*mm, 34*mm, 46*mm])
    ct.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),G1),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[WRM,PAL]),
        ("LINEBELOW",(0,0),(-1,-1),0.4,RUL),
        ("BOX",(0,0),(-1,-1),0.5,RUL),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(ct)
    story.append(SP(5))

    # Coûts
    story.append(P("③ ANALYSE DES COÛTS", size=11, bold=True, color=G1))
    story.append(SP(2))
    couts = [
        [P(h, size=8, color=white, bold=True, align=TA_CENTER) for h in ["Coût", "Manuel", machine_label, "Économie"]],
        [P("Coût / kg (DH)"),P(f"{r['cout_manuel_kg']} DH",align=TA_CENTER),P(f"{r['cout_machine_kg']} DH",align=TA_CENTER),P(f"{r['economie_kg']} DH/kg",color=G2,align=TA_CENTER)],
        [P("Coût / ha (DH)"),P(f"{r['cout_manuel_ha']:,} DH",align=TA_CENTER),P(f"{r['cout_machine_ha']:,} DH",align=TA_CENTER),P(f"{r['economie_ha']:,} DH",color=G2,align=TA_CENTER)],
        [P("Coût ferme total (DH)"),P(f"{r['cout_manuel_ferme']:,} DH",align=TA_CENTER),P(f"{r['cout_machine_ferme']:,} DH",align=TA_CENTER),P(f"{r['economie_ferme']:,} DH",color=G2,bold=True,align=TA_CENTER)],
    ]
    couttbl = Table(couts, colWidths=[52*mm, 34*mm, 34*mm, 46*mm])
    couttbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),OR),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[WRM,PAL]),
        ("LINEBELOW",(0,0),(-1,-1),0.4,RUL),
        ("BOX",(0,0),(-1,-1),0.5,RUL),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(couttbl)
    story.append(SP(5))

    # KPI + investissement
    if r["investissement"] > 0:
        story.append(P("④ INVESTISSEMENT & ROI", size=11, bold=True, color=G1))
        story.append(SP(2))
        kpi = [
            [P("Investissement total", size=9, bold=True), P(f"{r['investissement']:,} DH", size=10, bold=True, color=OR)],
            [P("Économie / saison", size=9, bold=True), P(f"{r['economie_ferme']:,} DH", size=10, bold=True, color=G2)],
        ]
        if r["payback"]:
            kpi.append([P("Payback", size=9, bold=True), P(f"{r['payback']} saisons", size=10, bold=True, color=G1)])
        kt = Table(kpi, colWidths=[80*mm, 86*mm])
        kt.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),PAL),
            ("LINEBELOW",(0,0),(-1,-1),0.4,RUL),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
            ("LINELEFT",(0,0),(0,-1),3,G1),
        ]))
        story.append(kt)

    doc.build(story)
    return buf.getvalue()

# ── KEYBOARDS ────────────────────────────────────────────
def machine_kb():
    return ReplyKeyboardMarkup([[m] for m in MACHINES.keys()], one_time_keyboard=True, resize_keyboard=True)
def batterie_kb():
    return ReplyKeyboardMarkup([[b] for b in BATTERIES.keys()], one_time_keyboard=True, resize_keyboard=True)
def chargeur_kb():
    return ReplyKeyboardMarkup([[c] for c in CHARGEURS.keys()], one_time_keyboard=True, resize_keyboard=True)
def access_kb():
    return ReplyKeyboardMarkup([[a] for a in ACCESSOIRES.keys()], one_time_keyboard=True, resize_keyboard=True)
def skip_kb():
    return ReplyKeyboardMarkup([[SKIP]], one_time_keyboard=True, resize_keyboard=True)

# ── HANDLERS ─────────────────────────────────────────────
async def cmd_start(u, c):
    await u.message.reply_text(
        "🫒 *Bot Simulation Récolte Olives — STIHL*\n\n"
        "Ce bot calcule et compare :\n"
        "• Récolte *manuelle* vs *machine STIHL*\n"
        "• Durée, coût, productivité, ROI\n\n"
        "Tape /simulation pour démarrer 🚀",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )

async def cmd_cancel(u, c):
    await u.message.reply_text("❌ Simulation annulée.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Étape 1
async def sim_start(u, c):
    c.user_data.clear()
    await u.message.reply_text(
        "🫒 *Nouvelle simulation*\n\n"
        "*Étape 1/9*\n"
        "📏 Quel est l'*écartement entre les arbres* sur une ligne ? (en mètres)\n"
        "_Ex: 6 pour 6 mètres_",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return S_ECART_ARBRE

async def s_ecart_arbre(u, c):
    try:
        val = float(u.message.text.replace(",", "."))
        if val <= 0: raise ValueError
        c.user_data["ecart_arbre"] = val
        await u.message.reply_text(
            f"✅ Écartement arbres : *{val}m*\n\n"
            "*Étape 2/9*\n"
            "📏 Écartement *entre les lignes* ? (en mètres)\n"
            "_Ex: 6 pour 6 mètres_",
            parse_mode="Markdown"
        )
        return S_ECART_LIGNE
    except:
        await u.message.reply_text("⚠️ Entrez un nombre valide (ex: 6)")
        return S_ECART_ARBRE

async def s_ecart_ligne(u, c):
    try:
        val = float(u.message.text.replace(",", "."))
        if val <= 0: raise ValueError
        c.user_data["ecart_ligne"] = val
        arbres_ha = round(10000 / (c.user_data["ecart_arbre"] * val), 1)
        await u.message.reply_text(
            f"✅ Écartement lignes : *{val}m*\n"
            f"→ Densité calculée : *{arbres_ha} arbres/ha* 🌳\n\n"
            "*Étape 3/9*\n"
            "🌍 Quelle est la *superficie totale* de la ferme ? (en hectares)\n"
            "_Ex: 10 pour 10 ha_",
            parse_mode="Markdown"
        )
        return S_SUPERFICIE
    except:
        await u.message.reply_text("⚠️ Entrez un nombre valide (ex: 6)")
        return S_ECART_LIGNE

async def s_superficie(u, c):
    try:
        val = float(u.message.text.replace(",", "."))
        if val <= 0: raise ValueError
        c.user_data["superficie"] = val
        arbres_ha = 10000 / (c.user_data["ecart_arbre"] * c.user_data["ecart_ligne"])
        total = round(arbres_ha * val, 0)
        await u.message.reply_text(
            f"✅ Superficie : *{val} ha*\n"
            f"→ Total arbres ferme : *{total:.0f} arbres* 🌳\n\n"
            "*Étape 4/9*\n"
            "🫒 Quel est le *rendement par arbre* ? (kg/arbre)\n"
            "_Ex: 100 pour 100 kg_",
            parse_mode="Markdown"
        )
        return S_RENDEMENT
    except:
        await u.message.reply_text("⚠️ Entrez un nombre valide (ex: 10)")
        return S_SUPERFICIE

async def s_rendement(u, c):
    try:
        val = float(u.message.text.replace(",", "."))
        if val <= 0: raise ValueError
        c.user_data["rendement"] = val
        arbres_ha = 10000 / (c.user_data["ecart_arbre"] * c.user_data["ecart_ligne"])
        prod_ha = round(arbres_ha * val / 1000, 2)
        await u.message.reply_text(
            f"✅ Rendement : *{val} kg/arbre*\n"
            f"→ Production/ha : *{prod_ha} tonnes/ha* 🫒\n\n"
            "*Étape 5/9*\n"
            "👷 *Durée manuelle par arbre* ? (en minutes)\n"
            "_Temps moyen qu'un ouvrier met pour récolter un arbre manuellement_\n"
            "_Ex: 90 pour 90 minutes_",
            parse_mode="Markdown"
        )
        return S_DUR_MANUEL
    except:
        await u.message.reply_text("⚠️ Entrez un nombre valide (ex: 100)")
        return S_RENDEMENT

async def s_dur_manuel(u, c):
    try:
        val = float(u.message.text.replace(",", "."))
        if val <= 0: raise ValueError
        c.user_data["dur_manuel"] = val
        arbres_j = round(480 / val, 1)
        await u.message.reply_text(
            f"✅ Durée manuelle : *{val} min/arbre*\n"
            f"→ Un ouvrier fait *{arbres_j} arbres/jour* 👷\n\n"
            "*Étape 6/9*\n"
            "⚙️ *Durée avec la machine SPA* par arbre ? (en minutes)\n"
            "_Ex: 45 pour 45 minutes_",
            parse_mode="Markdown"
        )
        return S_DUR_MACHINE
    except:
        await u.message.reply_text("⚠️ Entrez un nombre valide (ex: 90)")
        return S_DUR_MANUEL

async def s_dur_machine(u, c):
    try:
        val = float(u.message.text.replace(",", "."))
        if val <= 0: raise ValueError
        c.user_data["dur_machine"] = val
        arbres_j = round(480 / val, 1)
        gain = round((1 - val/c.user_data["dur_manuel"]) * 100, 0)
        await u.message.reply_text(
            f"✅ Durée machine : *{val} min/arbre*\n"
            f"→ Machine fait *{arbres_j} arbres/jour* ⚙️\n"
            f"→ Gain de vitesse : *{gain}%* plus rapide\n\n"
            "*Étape 7/9*\n"
            "👥 *Nombre d'opérateurs par machine* ?\n"
            "_Opérateur + aide(s) qui travaillent avec 1 machine_\n"
            "_Ex: 3_",
            parse_mode="Markdown"
        )
        return S_NB_OUV
    except:
        await u.message.reply_text("⚠️ Entrez un nombre valide (ex: 45)")
        return S_DUR_MACHINE

async def s_nb_ouv(u, c):
    try:
        val = int(u.message.text.strip())
        if val <= 0: raise ValueError
        c.user_data["nb_ouvriers"] = val
        await u.message.reply_text(
            f"✅ *{val} opérateurs* par machine\n\n"
            "*Étape 8/9*\n"
            "💰 *Coût d'un ouvrier* par jour ? (DH/jour)\n"
            "_Ex: 100 pour 100 DH/jour_",
            parse_mode="Markdown"
        )
        return S_COUT_OUV
    except:
        await u.message.reply_text("⚠️ Entrez un nombre entier (ex: 3)")
        return S_NB_OUV

async def s_cout_ouv(u, c):
    try:
        val = float(u.message.text.replace(",", "."))
        if val <= 0: raise ValueError
        c.user_data["cout_ouvrier"] = val
        await u.message.reply_text(
            f"✅ Coût ouvrier : *{val} DH/jour*\n\n"
            "*Étape 9/9*\n"
            "🎯 *Durée objectif de la campagne* ? (en jours)\n"
            "_En combien de jours tu veux finir la récolte ?_\n"
            "_Ex: 30 pour 30 jours_",
            parse_mode="Markdown"
        )
        return S_DUREE_CAMP
    except:
        await u.message.reply_text("⚠️ Entrez un nombre valide (ex: 100)")
        return S_COUT_OUV

async def s_duree_camp(u, c):
    try:
        val = int(u.message.text.strip())
        if val <= 0: raise ValueError
        c.user_data["duree_camp"] = val
        await u.message.reply_text(
            f"✅ Objectif campagne : *{val} jours*\n\n"
            "🔧 *Choix de la machine STIHL :*",
            parse_mode="Markdown",
            reply_markup=machine_kb()
        )
        return S_MACHINE
    except:
        await u.message.reply_text("⚠️ Entrez un nombre entier (ex: 30)")
        return S_DUREE_CAMP

async def s_machine(u, c):
    txt = u.message.text.strip()
    if txt not in MACHINES:
        await u.message.reply_text("⚠️ Choisis une machine dans la liste", reply_markup=machine_kb())
        return S_MACHINE
    c.user_data["machine_label"] = txt
    c.user_data["prix_machine"] = MACHINES[txt]
    await u.message.reply_text(
        f"✅ Machine : *{txt}* ({MACHINES[txt]:,} DH)\n\n"
        "🔋 *Choix de la batterie :*",
        parse_mode="Markdown", reply_markup=batterie_kb()
    )
    return S_BATTERIE

async def s_batterie(u, c):
    txt = u.message.text.strip()
    if txt not in BATTERIES:
        await u.message.reply_text("⚠️ Choisis une batterie dans la liste", reply_markup=batterie_kb())
        return S_BATTERIE
    c.user_data["prix_batterie"] = BATTERIES[txt]
    await u.message.reply_text(
        f"✅ Batterie : *{txt}*\n\n"
        "⚡ *Choix du chargeur :*",
        parse_mode="Markdown", reply_markup=chargeur_kb()
    )
    return S_CHARGEUR

async def s_chargeur(u, c):
    txt = u.message.text.strip()
    if txt not in CHARGEURS:
        await u.message.reply_text("⚠️ Choisis un chargeur", reply_markup=chargeur_kb())
        return S_CHARGEUR
    c.user_data["prix_chargeur"] = CHARGEURS[txt]
    await u.message.reply_text(
        f"✅ Chargeur : *{txt}*\n\n"
        "🎒 *Accessoires ?*",
        parse_mode="Markdown", reply_markup=access_kb()
    )
    return S_ACCESS

async def s_access(u, c):
    txt = u.message.text.strip()
    if txt not in ACCESSOIRES:
        await u.message.reply_text("⚠️ Choisis dans la liste", reply_markup=access_kb())
        return S_ACCESS
    c.user_data["prix_access"] = ACCESSOIRES[txt]

    # Calcul
    d = c.user_data
    r = calculer(d)

    # Résumé Telegram
    result_text = format_result(d, r)
    await u.message.reply_text(result_text, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

    # PDF
    msg = await u.message.reply_text("⏳ Génération du rapport PDF...")
    try:
        pdf = generate_pdf(d, r)
        await u.message.reply_document(
            document=pdf,
            filename=f"Simulation_Olives_STIHL_{d.get('machine_label','SPA').replace(' ','_')}.pdf",
            caption="📄 *Rapport complet — Simulation Récolte Olives STIHL*",
            parse_mode="Markdown"
        )
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Erreur PDF : {e}")

    return ConversationHandler.END

# ── MAIN ─────────────────────────────────────────────────
def main():
    from telegram.ext import ConversationHandler
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))

    TX = filters.TEXT & ~filters.COMMAND
    conv = ConversationHandler(
        entry_points=[CommandHandler("simulation", sim_start)],
        states={
            S_ECART_ARBRE:  [MessageHandler(TX, s_ecart_arbre)],
            S_ECART_LIGNE:  [MessageHandler(TX, s_ecart_ligne)],
            S_SUPERFICIE:   [MessageHandler(TX, s_superficie)],
            S_RENDEMENT:    [MessageHandler(TX, s_rendement)],
            S_DUR_MANUEL:   [MessageHandler(TX, s_dur_manuel)],
            S_DUR_MACHINE:  [MessageHandler(TX, s_dur_machine)],
            S_NB_OUV:       [MessageHandler(TX, s_nb_ouv)],
            S_COUT_OUV:     [MessageHandler(TX, s_cout_ouv)],
            S_DUREE_CAMP:   [MessageHandler(TX, s_duree_camp)],
            S_MACHINE:      [MessageHandler(TX, s_machine)],
            S_BATTERIE:     [MessageHandler(TX, s_batterie)],
            S_CHARGEUR:     [MessageHandler(TX, s_chargeur)],
            S_ACCESS:       [MessageHandler(TX, s_access)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )
    app.add_handler(conv)

    print("🟢 Bot Olive STIHL démarré !")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

main()
