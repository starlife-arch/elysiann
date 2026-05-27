import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for

from utils.cloudinary import upload_user_photos
from utils.firebase_config import get_auth, get_firestore
from utils.invite import generate_invite_code, validate_invite_code
from utils.payments import create_pesapal_checkout, create_stripe_checkout

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-in-production")


def utcnow():
    return datetime.now(timezone.utc)


def db():
    return get_firestore()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("uid"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def get_user(uid):
    doc = db().collection("users").document(uid).get()
    return doc.to_dict() if doc.exists else None


def get_user_by_email(email):
    results = db().collection("users").where("email", "==", email.lower()).limit(1).stream()
    for doc in results:
        return doc.to_dict()
    return None


def has_member_access(user):
    if not user or user.get("banned"):
        return False
    now = utcnow()
    if user.get("manual_access"):
        expiry = user.get("access_expiry_date")
        if expiry and expiry < now:
            db().collection("users").document(user["uid"]).update({"manual_access": False})
            return False
        return True
    return bool(user.get("invite_used") and user.get("paid"))


def get_public_profiles(current_uid):
    profiles = []
    for d in db().collection("users").where("status", "==", "approved").stream():
        user = d.to_dict()
        if user.get("uid") == current_uid:
            continue
        profiles.append({
            "uid": user.get("uid"),
            "full_name": user.get("full_name"),
            "age": user.get("age"),
            "city": user.get("city"),
            "country": user.get("country"),
            "bio": user.get("bio"),
            "profile_interests": user.get("profile_interests") or user.get("interests") or [],
            "photo_urls": user.get("photo_urls") or [],
            "badge_verified": user.get("badge_verified", False),
        })
    return profiles


def has_match(uid1, uid2):
    a = db().collection("likes").document(f"{uid1}_{uid2}").get().exists
    b = db().collection("likes").document(f"{uid2}_{uid1}").get().exists
    return a and b


@app.context_processor
def inject_auth():
    return {"auth_enabled": bool(get_auth())}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Please enter your email address.", "error")
            return redirect(url_for("login"))
        user = get_user_by_email(email)
        if not user:
            flash("No account found for that email. Please apply for membership first.", "error")
            return redirect(url_for("apply"))
        if user.get("banned"):
            flash("Account suspended. Contact support.", "error")
            return redirect(url_for("login"))
        if user.get("status") == "pending":
            session["pending_uid"] = user["uid"]
            return redirect(url_for("pending_verification"))
        if user.get("status") == "rejected":
            flash("Your application was not approved at this time.", "error")
            return redirect(url_for("login"))
        session["uid"] = user["uid"]
        return redirect(url_for("post_login_gate"))
    return render_template("login.html")


@app.route("/apply", methods=["GET", "POST"])
def apply():
    if request.method == "POST":
        age = int(request.form.get("age", "0"))
        if age < 18:
            flash("Applicants must be 18+.", "error")
            return redirect(url_for("apply"))
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Email address is required.", "error")
            return redirect(url_for("apply"))
        if get_user_by_email(email):
            flash("An application already exists for this email.", "error")
            return redirect(url_for("login"))

        uid = str(uuid.uuid5(uuid.NAMESPACE_URL, email))
        photo_urls = upload_user_photos(request.files.getlist("photos"), folder="private-dating")
        user_payload = {
            "uid": uid,
            "full_name": request.form.get("full_name", "").strip(),
            "age": age,
            "gender": request.form.get("gender", "").strip(),
            "country": request.form.get("country", "").strip(),
            "city": request.form.get("city", "").strip(),
            "email": email,
            "phone": request.form.get("phone", "").strip(),
            "video_call_window": request.form.get("video_call_window", "").strip(),
            "interests": [i.strip() for i in request.form.get("interests", "").split(",") if i.strip()],
            "profile_interests": [i.strip() for i in request.form.get("interests", "").split(",") if i.strip()],
            "video_verification_status": "pending",
            "badge_verified": False,
            "bio": request.form.get("bio", "").strip(),
            "photo_urls": photo_urls,
            "status": "pending",
            "invite_code": None,
            "invite_used": False,
            "paid": False,
            "payment_provider": None,
            "manual_access": False,
            "access_start_date": None,
            "access_expiry_date": None,
            "banned": False,
            "role": "user",
            "created_at": utcnow(),
        }
        db().collection("users").document(uid).set(user_payload, merge=True)
        flash("Application submitted! We'll review it within 48 hours.", "success")
        return redirect(url_for("login"))
    return render_template("apply.html")


@app.route("/pending")
def pending_verification():
    uid = session.get("pending_uid")
    if not uid:
        return redirect(url_for("login"))
    user = get_user(uid)
    if not user:
        return redirect(url_for("login"))
    return render_template("pending.html", user=user)


@app.route("/post-login")
@login_required
def post_login_gate():
    user = get_user(session["uid"])
    if has_member_access(user):
        return redirect(url_for("dashboard"))
    if user.get("invite_override") or user.get("invite_used"):
        return redirect(url_for("payment"))
    return redirect(url_for("invite"))


@app.route("/invite", methods=["GET", "POST"])
@login_required
def invite():
    uid = session["uid"]
    if request.method == "POST":
        valid, message = validate_invite_code(db(), uid, request.form.get("invite_code", "").strip().upper())
        flash(message, "success" if valid else "error")
        if valid:
            return redirect(url_for("payment"))
    return render_template("invite.html")


@app.route("/payment", methods=["GET", "POST"])
@login_required
def payment():
    uid = session["uid"]
    if request.method == "POST":
        provider = request.form.get("provider")
        checkout_url = create_stripe_checkout(uid) if provider == "stripe" else create_pesapal_checkout(uid)
        db().collection("users").document(uid).update({"paid": True, "payment_provider": provider})
        flash(f"Payment initiated via {provider}.", "success")
        return redirect(checkout_url)
    return render_template("payment.html")


@app.route("/dashboard")
@login_required
def dashboard():
    user = get_user(session["uid"])
    if user.get("banned"):
        flash("Account suspended.", "error")
        session.clear()
        return redirect(url_for("login"))
    if not has_member_access(user):
        return redirect(url_for("post_login_gate"))
    profiles = get_public_profiles(user["uid"])
    return render_template("dashboard.html", user=user, profiles=profiles)


@app.route("/swipe", methods=["POST"])
@login_required
def swipe():
    actor_uid = session["uid"]
    target_uid = request.form.get("target_uid")
    direction = request.form.get("direction")
    if direction == "left":
        db().collection("likes").document(f"{actor_uid}_{target_uid}").set({"from_uid": actor_uid, "to_uid": target_uid, "created_at": utcnow()})
        if has_match(actor_uid, target_uid):
            flash("It's a match! You can now message each other.", "success")
    else:
        db().collection("passes").document(f"{actor_uid}_{target_uid}").set({"from_uid": actor_uid, "to_uid": target_uid, "created_at": utcnow()})
    return redirect(url_for("dashboard"))


@app.route("/messages")
@login_required
def messages_tab():
    uid = session["uid"]
    inbox = [m.to_dict() for m in db().collection("messages").where("to_uid", "==", uid).stream()]
    outbox = [m.to_dict() for m in db().collection("messages").where("from_uid", "==", uid).stream()]
    for m in inbox:
        sender = get_user(m.get("from_uid"))
        m["from_name"] = sender.get("full_name") if sender else m.get("from_uid")
    matched_uids = []
    for doc in db().collection("likes").where("from_uid", "==", uid).stream():
        to_uid = doc.to_dict().get("to_uid")
        if has_match(uid, to_uid):
            matched_uids.append(to_uid)
    matched_users = [get_user(x) for x in matched_uids if get_user(x)]
    return render_template("messages.html", inbox=inbox, outbox=outbox, matched_users=matched_users)


@app.route("/message", methods=["POST"])
@login_required
def send_message():
    from_uid = session["uid"]
    to_uid = request.form.get("to_uid")
    text = request.form.get("message", "").strip()
    if not has_match(from_uid, to_uid):
        flash("Messaging is unlocked only after both users like each other.", "error")
        return redirect(url_for("messages_tab"))
    if to_uid and text:
        db().collection("messages").document(str(uuid.uuid4())).set({"from_uid": from_uid, "to_uid": to_uid, "message": text, "created_at": utcnow()})
        flash("Message sent.", "success")
    return redirect(url_for("messages_tab"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_tab():
    uid = session["uid"]
    user = get_user(uid)
    if request.method == "POST":
        interests = [i.strip() for i in request.form.get("interests", "").split(",") if i.strip()]
        payload = {"bio": request.form.get("bio", "").strip(), "profile_interests": interests}
        files = request.files.getlist("photos")
        if files and any(getattr(f, 'filename', '') for f in files):
            payload["photo_urls"] = upload_user_photos(files, folder="private-dating")
        db().collection("users").document(uid).update(payload)
        flash("Profile settings updated.", "success")
        return redirect(url_for("settings_tab"))
    return render_template("settings.html", user=user)


@app.route("/premium")
@login_required
def premium_tab():
    return render_template("premium.html")


def role_level(role):
    return {"user": 1, "moderator": 2, "admin": 3, "super_admin": 4}.get(role, 1)


def admin_required(min_role="admin"):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            actor = get_user(session.get("uid")) if session.get("uid") else None
            if not actor or role_level(actor.get("role", "user")) < role_level(min_role):
                flash("Admin permission required.", "error")
                return redirect(url_for("login"))
            return fn(*args, **kwargs)
        return wrapper
    return deco


@app.route("/admin", methods=["GET", "POST"])
@login_required
@admin_required("admin")
def admin_dashboard():
    if request.method == "POST":
        action = request.form.get("action")
        target_uid = request.form.get("target_uid")
        ref = db().collection("users").document(target_uid)
        if action == "approve":
            ref.update({"status": "approved", "admin_access_code": str(uuid.uuid4())[:8].upper(), "invite_code": generate_invite_code(), "invite_used": False})
        elif action == "reject":
            ref.update({"status": "rejected"})
        elif action == "manual_access":
            days = request.form.get("days", "30")
            start = utcnow()
            expiry = None if days == "permanent" else start + timedelta(days=int(days))
            ref.update({"manual_access": True, "access_start_date": start, "access_expiry_date": expiry})
        elif action == "revoke_manual_access":
            ref.update({"manual_access": False, "access_start_date": None, "access_expiry_date": None})
        elif action == "ban":
            ref.update({"banned": True})
        elif action == "unban":
            ref.update({"banned": False})
        elif action == "verify_badge":
            ref.update({"badge_verified": True, "video_verification_status": "verified"})
        flash("Admin action completed.", "success")
        return redirect(url_for("admin_dashboard"))

    users = [d.to_dict() for d in db().collection("users").stream()]
    now = utcnow()
    stats = {"pending": sum(u.get("status") == "pending" for u in users), "approved": sum(u.get("status") == "approved" for u in users), "paid": sum(bool(u.get("paid")) for u in users), "manual": sum(bool(u.get("manual_access")) for u in users), "banned": sum(bool(u.get("banned")) for u in users), "expired": sum(bool(u.get("access_expiry_date") and u["access_expiry_date"] < now) for u in users)}
    return render_template("admin.html", users=users, stats=stats)


@app.errorhandler(Exception)
def handle_exception(exc):
    app.logger.exception("Unhandled error: %s", exc)
    return render_template("error.html", error="Service temporarily unavailable."), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
