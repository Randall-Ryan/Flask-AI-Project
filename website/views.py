from flask import Blueprint, render_template, request, flash, jsonify
from flask_login import login_required, current_user
from .models import Note, User
import json
from . import db
import os
import openai

openai.organization = os.getenv("OPENAI_ORGANIZATION")
openai.api_key = os.getenv("OPENAI_API_KEY")
views = Blueprint("views", __name__)


@views.route("/testing", methods=["GET", "POST"])
@login_required
def testing():
    notes = Note.query.all()
    users = User.query.all()
    return render_template("testing.html", notes=notes, users=users, user=current_user)


@views.route("/create-note", methods=["GET", "POST"])
@login_required
def create_note():
    if request.method == "POST":
        note = request.form.get("note")

        if len(note) < 1:
            flash("Note is too short!", category="error")
        else:
            new_note = Note(data=note, user_id=current_user.id)
            x = openai.Image.create(prompt=note, n=1, size="512x512")
            new_note.img_src = x["data"][0]["url"]
            db.session.add(new_note)
            db.session.commit()
            flash("Note added!", category="success")
            return render_template("my_notes.html", user=current_user)
    return render_template("create_note.html", user=current_user)


@views.route("/all-notes", methods=["GET", "POST"])
@login_required
def view_all_notes():
    notes = Note.query.all()
    return render_template("all_notes.html", notes=notes, user=current_user)


@views.route("/note/", defaults={"id": 1})
@views.route("/note/<int:id>", methods=["GET", "POST"])
@login_required
def view_note(id):
    note = Note.query.get(id)
    return render_template("note.html", note=note, user=current_user)


@views.route("/", methods=["GET", "POST"])
@login_required
def home():
    return render_template("home.html", user=current_user)


@views.route("/my-account", methods=["GET", "POST"])
@login_required
def my_account():
    return render_template(
        "account.html", user=current_user, note_count=len(current_user.notes)
    )


@views.route("/my-notes", methods=["GET"])
@login_required
def my_notes():
    return render_template("my_notes.html", user=current_user)


@views.route("/delete-note", methods=["POST"])
def delete_note():
    note = json.loads(request.data)
    noteId = note["noteId"]
    note = Note.query.get(noteId)

    if note:
        if note.user_id == current_user.id:
            db.session.delete(note)
            db.session.commit()
            return jsonify({})
