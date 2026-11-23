import os, json, secrets, sqlite3
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta, date
from functools import wraps
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_file, g
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor, white

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, instance_relative_config=True)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "troque-esta-chave-no-ambiente"),
    DATABASE=os.path.join(app.instance_path, "database.db"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
os.makedirs(app.instance_path, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "certificates"), exist_ok=True)
csrf = CSRFProtect(app)

def db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None: conn.close()

def now():
    return datetime.now().isoformat(timespec="seconds")

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, department TEXT NOT NULL, role TEXT, password_hash TEXT, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, activated_at TEXT);
    CREATE TABLE IF NOT EXISTS invites(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), token TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, used_at TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS modules(id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL, objectives_json TEXT NOT NULL, sections_json TEXT NOT NULL, position INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, module_id INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE, prompt TEXT NOT NULL, reference TEXT NOT NULL, position INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS options(id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE, text TEXT NOT NULL, is_correct INTEGER NOT NULL DEFAULT 0, position INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS progress(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), module_id INTEGER NOT NULL REFERENCES modules(id), content_completed INTEGER NOT NULL DEFAULT 0, assessment_passed INTEGER NOT NULL DEFAULT 0, completed_at TEXT, UNIQUE(employee_id,module_id));
    CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), module_id INTEGER NOT NULL REFERENCES modules(id), score REAL NOT NULL, passed INTEGER NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS answers(id INTEGER PRIMARY KEY, attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE, question_id INTEGER NOT NULL REFERENCES questions(id), option_id INTEGER NOT NULL REFERENCES options(id));
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS certificates(id INTEGER PRIMARY KEY, employee_id INTEGER UNIQUE NOT NULL REFERENCES employees(id), code TEXT UNIQUE NOT NULL, completion_date TEXT NOT NULL, training_name TEXT NOT NULL);
    """)
    if not conn.execute("SELECT 1 FROM admins LIMIT 1").fetchone():
        conn.execute("INSERT INTO admins(name,email,password_hash) VALUES(?,?,?)",("Administrador RH","admin@evonik.local",generate_password_hash("Evonik@2026!")))
    conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('pass_score','70')")
    course = json.load(open(os.path.join(BASE_DIR,"course","course.json"),encoding="utf-8"))
    if not conn.execute("SELECT 1 FROM modules LIMIT 1").fetchone():
        for idx,m in enumerate(course["modules"],1):
            cur=conn.execute("INSERT INTO modules(slug,title,description,objectives_json,sections_json,position) VALUES(?,?,?,?,?,?)",
                (m["slug"],m["title"],m["description"],json.dumps(m["objectives"],ensure_ascii=False),json.dumps(m["sections"],ensure_ascii=False),idx))
            mid=cur.lastrowid
            for qi,q in enumerate(m["questions"],1):
                qid=conn.execute("INSERT INTO questions(module_id,prompt,reference,position) VALUES(?,?,?,?)",(mid,q["prompt"],q["reference"],qi)).lastrowid
                for oi,opt in enumerate(q["options"],1):
                    conn.execute("INSERT INTO options(question_id,text,is_correct,position) VALUES(?,?,?,?)",(qid,opt,1 if oi-1==q["correct"] else 0,oi))
    if not conn.execute("SELECT 1 FROM employees LIMIT 1").fetchone():
        # Colaborador 1: convite pendente
        a=conn.execute("INSERT INTO employees(name,email,department,role,status,created_at) VALUES(?,?,?,?,?,?)",
            ("Ana Martins","ana.martins@evonik.local","Produção","Operadora","pending",now())).lastrowid
        conn.execute("INSERT INTO invites(employee_id,token,expires_at,created_at) VALUES(?,?,?,?)",
            (a,"demo-convite-ana-2026",(datetime.now()+timedelta(days=30)).isoformat(timespec="seconds"),now()))
        # Colaborador 2: treinamento em andamento
        b=conn.execute("INSERT INTO employees(name,email,department,role,password_hash,status,created_at,activated_at) VALUES(?,?,?,?,?,?,?,?)",
            ("Bruno Costa","bruno.costa@evonik.local","Manutenção","Técnico",generate_password_hash("Colab@2026!"),"active",now(),now())).lastrowid
        first=conn.execute("SELECT id FROM modules ORDER BY position LIMIT 1").fetchone()["id"]
        conn.execute("INSERT INTO progress(employee_id,module_id,content_completed,assessment_passed,completed_at) VALUES(?,?,?,?,?)",(b,first,1,1,now()))
        second=conn.execute("SELECT id FROM modules ORDER BY position LIMIT 1 OFFSET 1").fetchone()["id"]
        conn.execute("INSERT INTO progress(employee_id,module_id,content_completed) VALUES(?,?,1)",(b,second))
        # Colaborador 3: curso concluído
        c=conn.execute("INSERT INTO employees(name,email,department,role,password_hash,status,created_at,activated_at) VALUES(?,?,?,?,?,?,?,?)",
            ("Carla Souza","carla.souza@evonik.local","Qualidade","Analista",generate_password_hash("Colab@2026!"),"active",now(),now())).lastrowid
        for mrow in conn.execute("SELECT id FROM modules ORDER BY position").fetchall():
            conn.execute("INSERT INTO progress(employee_id,module_id,content_completed,assessment_passed,completed_at) VALUES(?,?,?,?,?)",(c,mrow["id"],1,1,now()))
        code="EVK-DEMO-2026-0003"
        conn.execute("INSERT INTO certificates(employee_id,code,completion_date,training_name) VALUES(?,?,?,?)",(c,code,date.today().isoformat(),course["training_name"]))
        # Histórico fictício para demonstrar notas e tentativas no painel RH
        for mrow in conn.execute("SELECT id FROM modules ORDER BY position").fetchall():
            conn.execute("INSERT INTO attempts(employee_id,module_id,score,passed,created_at) VALUES(?,?,?,?,?)",(c,mrow["id"],100,1,now()))
        conn.execute("INSERT INTO attempts(employee_id,module_id,score,passed,created_at) VALUES(?,?,?,?,?)",(b,second,50,0,now()))
    conn.commit()

def current_user():
    if not session.get("user_id"): return None
    if session.get("role")=="admin":
        return db().execute("SELECT id,name,email FROM admins WHERE id=?",(session["user_id"],)).fetchone()
    return db().execute("SELECT id,name,email,department,role,status FROM employees WHERE id=?",(session["user_id"],)).fetchone()

@app.context_processor
def inject_globals():
    return {"current_user":current_user(),"user_role":session.get("role")}

def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            if not session.get("user_id"): return redirect(url_for("login"))
            if role and session.get("role")!=role: abort(403)
            return fn(*args,**kwargs)
        return wrapped
    return deco

def modules():
    rows=db().execute("SELECT * FROM modules ORDER BY position").fetchall()
    return rows

def module_status(employee_id, module_rows):
    result=[]
    previous_done=True
    for m in module_rows:
        p=db().execute("SELECT * FROM progress WHERE employee_id=? AND module_id=?",(employee_id,m["id"])).fetchone()
        passed=bool(p and p["assessment_passed"])
        content=bool(p and p["content_completed"])
        status="concluido" if passed else ("andamento" if content else ("disponivel" if previous_done else "bloqueado"))
        result.append({"module":m,"progress":p,"status":status,"passed":passed,"content":content})
        previous_done=passed
    return result

@app.route("/")
def index():
    if session.get("role")=="admin": return redirect(url_for("admin_dashboard"))
    if session.get("role")=="employee": return redirect(url_for("employee_dashboard"))
    return redirect(url_for("login"))

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        admin=db().execute("SELECT * FROM admins WHERE lower(email)=?",(email,)).fetchone()
        if admin and check_password_hash(admin["password_hash"],password):
            session.clear(); session.update(user_id=admin["id"],role="admin")
            return redirect(url_for("admin_dashboard"))
        emp=db().execute("SELECT * FROM employees WHERE lower(email)=?",(email,)).fetchone()
        if emp and emp["password_hash"] and check_password_hash(emp["password_hash"],password):
            session.clear(); session.update(user_id=emp["id"],role="employee")
            return redirect(url_for("employee_dashboard"))
        flash("E-mail ou senha inválidos.","error")
    return render_template("login.html")

@app.route("/logout",methods=["POST"])
def logout():
    session.clear(); flash("Você saiu da plataforma.","success"); return redirect(url_for("login"))

@app.route("/ativar/<token>",methods=["GET","POST"])
def activate(token):
    inv=db().execute("SELECT i.*,e.name,e.email,e.department,e.role,e.status FROM invites i JOIN employees e ON e.id=i.employee_id WHERE i.token=?",(token,)).fetchone()
    if not inv or inv["used_at"] or inv["status"]!="pending" or inv["expires_at"]<now():
        flash("Convite inválido, expirado ou já utilizado.","error"); return redirect(url_for("login"))
    if request.method=="POST":
        pw=request.form.get("password",""); confirm=request.form.get("confirm_password","")
        if len(pw)<10: flash("A senha deve ter pelo menos 10 caracteres.","error")
        elif pw!=confirm: flash("As senhas não coincidem.","error")
        else:
            db().execute("UPDATE employees SET password_hash=?,status='active',activated_at=? WHERE id=?",(generate_password_hash(pw),now(),inv["employee_id"]))
            db().execute("UPDATE invites SET used_at=? WHERE id=?",(now(),inv["id"]))
            db().commit()
            flash("Conta ativada. Faça login para iniciar.","success"); return redirect(url_for("login"))
    return render_template("activation.html",invite=inv)

@app.route("/recuperar-senha",methods=["GET","POST"])
def recovery():
    if request.method=="POST":
        flash("Tela demonstrativa: a recuperação por e-mail ainda não está integrada. Solicite suporte ao RH.","info")
    return render_template("recovery.html")

@app.route("/colaborador")
@login_required("employee")
def employee_dashboard():
    employee=current_user(); ms=module_status(employee["id"],modules())
    done=sum(1 for x in ms if x["passed"]); total=len(ms)
    pct=round(done/total*100) if total else 0
    next_item=next((x for x in ms if x["status"] in ("disponivel","andamento")),None)
    cert=db().execute("SELECT * FROM certificates WHERE employee_id=?",(employee["id"],)).fetchone()
    return render_template("employee/dashboard.html",employee=employee,items=ms,done=done,total=total,pct=pct,next_item=next_item,certificate=cert)

@app.route("/modulo/<int:module_id>")
@login_required("employee")
def training(module_id):
    employee=current_user(); ms=module_status(employee["id"],modules())
    item=next((x for x in ms if x["module"]["id"]==module_id),None)
    if not item: abort(404)
    if item["status"]=="bloqueado": abort(403)
    m=item["module"]
    if item["passed"]: flash("Este módulo já foi concluído.","info")
    return render_template("employee/training.html",item=item,sections=json.loads(m["sections_json"]),objectives=json.loads(m["objectives_json"]))

@app.route("/modulo/<int:module_id>/concluir-conteudo",methods=["POST"])
@login_required("employee")
def complete_content(module_id):
    employee=current_user(); ms=module_status(employee["id"],modules())
    item=next((x for x in ms if x["module"]["id"]==module_id),None)
    if not item or item["status"]=="bloqueado": abort(403)
    db().execute("INSERT INTO progress(employee_id,module_id,content_completed) VALUES(?,?,1) ON CONFLICT(employee_id,module_id) DO UPDATE SET content_completed=1",(employee["id"],module_id))
    db().commit()
    return redirect(url_for("assessment",module_id=module_id))

@app.route("/modulo/<int:module_id>/avaliacao",methods=["GET","POST"])
@login_required("employee")
def assessment(module_id):
    employee=current_user(); ms=module_status(employee["id"],modules())
    item=next((x for x in ms if x["module"]["id"]==module_id),None)
    if not item or item["status"]=="bloqueado": abort(403)
    if not item["content"]: abort(403)
    qs=db().execute("SELECT * FROM questions WHERE module_id=? ORDER BY position",(module_id,)).fetchall()
    if request.method=="POST":
        submitted=[]
        for q in qs:
            oid=request.form.get(f"q_{q['id']}",type=int)
            opt=db().execute("SELECT * FROM options WHERE id=? AND question_id=?",(oid,q["id"])).fetchone() if oid else None
            if not opt: flash("Responda todas as questões antes de enviar.","error"); return redirect(url_for("assessment",module_id=module_id))
            submitted.append((q,opt))
        correct=sum(1 for q,o in submitted if o["is_correct"])
        score=round(correct/len(qs)*100,2) if qs else 0
        threshold=float(db().execute("SELECT value FROM settings WHERE key='pass_score'").fetchone()["value"])
        passed=score>=threshold
        cur=db().execute("INSERT INTO attempts(employee_id,module_id,score,passed,created_at) VALUES(?,?,?,?,?)",(employee["id"],module_id,score,int(passed),now()))
        aid=cur.lastrowid
        for q,o in submitted: db().execute("INSERT INTO answers(attempt_id,question_id,option_id) VALUES(?,?,?)",(aid,q["id"],o["id"]))
        if passed:
            db().execute("INSERT INTO progress(employee_id,module_id,content_completed,assessment_passed,completed_at) VALUES(?,?,1,1,?) ON CONFLICT(employee_id,module_id) DO UPDATE SET content_completed=1,assessment_passed=1,completed_at=excluded.completed_at",(employee["id"],module_id,now()))
            all_ms=module_status(employee["id"],modules())
            if all(x["passed"] or x["module"]["id"]==module_id for x in all_ms):
                # Certificate is issued only after every module is approved
                db().execute("INSERT OR IGNORE INTO certificates(employee_id,code,completion_date,training_name) VALUES(?,?,?,?)",
                    (employee["id"],"EVK-"+secrets.token_hex(4).upper(),date.today().isoformat(),"Integração de Segurança do Trabalho"))
        db().commit()
        return render_template("employee/result.html",score=score,passed=passed,threshold=threshold,module=item["module"],next_url=url_for("employee_dashboard"))
    questions=[]
    for q in qs:
        options=db().execute("SELECT id,text FROM options WHERE question_id=? ORDER BY position",(q["id"],)).fetchall()
        questions.append({"id":q["id"],"prompt":q["prompt"],"options":options})
    return render_template("employee/assessment.html",module=item["module"],questions=questions)

@app.route("/certificado")
@login_required("employee")
def certificate():
    employee=current_user()
    cert=db().execute("SELECT * FROM certificates WHERE employee_id=?",(employee["id"],)).fetchone()
    if not cert: abort(403)
    return render_template("employee/certificate.html",employee=employee,certificate=cert)

@app.route("/certificado/pdf")
@login_required("employee")
def certificate_pdf():
    employee=current_user(); cert=db().execute("SELECT * FROM certificates WHERE employee_id=?",(employee["id"],)).fetchone()
    if not cert: abort(403)
    buf=BytesIO(); c=canvas.Canvas(buf,pagesize=landscape(A4)); w,h=landscape(A4)
    c.setFillColor(HexColor("#981B81")); c.rect(0,h-22,w,22,fill=1,stroke=0)
    logo_path=os.path.join(BASE_DIR,"static","images","logo","evonik-logo.png")
    if os.path.exists(logo_path):
        try:
            c.drawImage(ImageReader(logo_path),42,h-88,width=105,height=38,preserveAspectRatio=True,mask="auto",anchor="c")
        except Exception:
            pass
    c.setFillColor(HexColor("#222226")); c.setFont("Helvetica-Bold",28); c.drawCentredString(w/2,h-115,"CERTIFICADO DE CONCLUSÃO")
    c.setFillColor(HexColor("#666666")); c.setFont("Helvetica",14); c.drawCentredString(w/2,h-155,"EVONIK | Integração de Segurança do Trabalho")
    c.setFillColor(HexColor("#222226")); c.setFont("Helvetica",15); c.drawCentredString(w/2,h-225,"Certificamos que")
    c.setFont("Helvetica-Bold",25); c.drawCentredString(w/2,h-270,employee["name"])
    c.setFont("Helvetica",14); c.drawCentredString(w/2,h-315,"concluiu o treinamento de Integração de Segurança do Trabalho.")
    c.setFont("Helvetica",12); c.drawCentredString(w/2,h-355,f"Data de conclusão: {cert['completion_date']}")
    c.setStrokeColor(HexColor("#981B81")); c.line(w/2-120,105,w/2+120,105)
    c.setFont("Helvetica",10); c.setFillColor(HexColor("#666666")); c.drawCentredString(w/2,88,"Identificação / assinatura do responsável")
    c.drawString(40,35,f"Código de validação: {cert['code']}")
    c.save(); buf.seek(0)
    return send_file(buf,as_attachment=True,download_name="certificado-evonik.pdf",mimetype="application/pdf")

@app.route("/rh")
@login_required("admin")
def admin_dashboard():
    conn=db()
    total=conn.execute("SELECT COUNT(*) n FROM employees").fetchone()["n"]
    pending=conn.execute("SELECT COUNT(*) n FROM employees WHERE status='pending'").fetchone()["n"]
    done=conn.execute("SELECT COUNT(*) n FROM certificates").fetchone()["n"]
    active=conn.execute("SELECT COUNT(*) n FROM employees WHERE status='active'").fetchone()["n"]-done
    employees=conn.execute("SELECT * FROM employees ORDER BY name").fetchall()
    mlist=modules()
    rows=[]
    for e in employees:
        st=module_status(e["id"],mlist); progress=round(sum(x["passed"] for x in st)/len(st)*100) if st else 0
        cert=conn.execute("SELECT completion_date FROM certificates WHERE employee_id=?",(e["id"],)).fetchone()
        avg=conn.execute("SELECT AVG(score) value FROM attempts WHERE employee_id=?",(e["id"],)).fetchone()["value"]
        rows.append({"employee":e,"progress":progress,"certificate":cert,"average":round(avg,1) if avg is not None else None})
    return render_template("admin/dashboard.html",total=total,pending=pending,done=done,active=active,employees=rows)

@app.route("/rh/colaboradores/novo",methods=["GET","POST"])
@login_required("admin")
def new_employee():
    if request.method=="POST":
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower()
        dept=request.form.get("department","").strip(); role=request.form.get("role","").strip()
        if not name or not email or not dept: flash("Preencha nome, e-mail e departamento.","error")
        else:
            try:
                eid=db().execute("INSERT INTO employees(name,email,department,role,status,created_at) VALUES(?,?,?,?,?,?)",(name,email,dept,role,"pending",now())).lastrowid
                token=secrets.token_urlsafe(32)
                db().execute("INSERT INTO invites(employee_id,token,expires_at,created_at) VALUES(?,?,?,?)",(eid,token,(datetime.now()+timedelta(days=7)).isoformat(timespec="seconds"),now()))
                db().commit()
                invite_url=url_for("activate",token=token,_external=True)
                return render_template("admin/invite_created.html",invite_url=invite_url,name=name)
            except sqlite3.IntegrityError: flash("Já existe um colaborador com esse e-mail.","error")
    return render_template("admin/new_employee.html")

@app.route("/rh/colaborador/<int:employee_id>")
@login_required("admin")
def employee_detail(employee_id):
    e=db().execute("SELECT * FROM employees WHERE id=?",(employee_id,)).fetchone()
    if not e: abort(404)
    ms=module_status(employee_id,modules())
    attempts=db().execute("SELECT a.*,m.title FROM attempts a JOIN modules m ON m.id=a.module_id WHERE a.employee_id=? ORDER BY a.created_at DESC",(employee_id,)).fetchall()
    cert=db().execute("SELECT * FROM certificates WHERE employee_id=?",(employee_id,)).fetchone()
    invite=db().execute("SELECT * FROM invites WHERE employee_id=? ORDER BY id DESC LIMIT 1",(employee_id,)).fetchone()
    return render_template("admin/employee_detail.html",employee=e,items=ms,attempts=attempts,certificate=cert,invite=invite)

@app.route("/rh/curso")
@login_required("admin")
def course_review():
    return render_template("admin/course.html",modules=modules(),threshold=db().execute("SELECT value FROM settings WHERE key='pass_score'").fetchone()["value"])

@app.route("/rh/curso/nota",methods=["POST"])
@login_required("admin")
def update_threshold():
    try: value=float(request.form.get("pass_score","70"))
    except ValueError: value=70
    if value<1 or value>100: flash("A nota deve estar entre 1 e 100.","error")
    else:
        db().execute("UPDATE settings SET value=? WHERE key='pass_score'",(str(value),)); db().commit(); flash("Nota mínima atualizada.","success")
    return redirect(url_for("course_review"))

@app.route("/rh/curso/modulo/<int:module_id>")
@login_required("admin")
def module_review(module_id):
    m=db().execute("SELECT * FROM modules WHERE id=?",(module_id,)).fetchone()
    if not m: abort(404)
    questions=db().execute("SELECT * FROM questions WHERE module_id=? ORDER BY position",(module_id,)).fetchall()
    items=[]
    for q in questions:
        opts=db().execute("SELECT * FROM options WHERE question_id=? ORDER BY position",(q["id"],)).fetchall()
        items.append({"question":q,"options":opts})
    return render_template("admin/module_review.html",module=m,sections=json.loads(m["sections_json"]),objectives=json.loads(m["objectives_json"]),questions=items)

@app.errorhandler(403)
def forbidden(e): return render_template("error.html",code=403,message="Você não tem permissão para acessar este conteúdo."),403
@app.errorhandler(404)
def not_found(e): return render_template("error.html",code=404,message="Página não encontrada."),404

with app.app_context():
    init_db()

if __name__=="__main__":
    app.run(debug=True)
