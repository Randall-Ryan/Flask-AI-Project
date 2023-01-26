import base64
import io
from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for
from flask_login import login_required, current_user
from .models import Note, User
import json
from . import db
import os
import openai
from riotwatcher import LolWatcher, ApiError
import urllib
import matplotlib.pyplot as plot
import fortnite_api

my_region = "na1"
fortnite_api_key = os.environ["FORTNITE_API_KEY"]
league_api_key = os.environ["LEAGUE_API_KEY"]
lol_watcher = LolWatcher(league_api_key)

openai.organization = os.getenv("OPENAI_ORGANIZATION")
openai.api_key = os.getenv("OPENAI_API_KEY")

fort_api = fortnite_api.FortniteAPI(api_key=fortnite_api_key)
views = Blueprint("views", __name__)


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


@views.route("/match/", defaults={"id": 1})
@views.route("/match/<string:summoner>", methods=["GET", "POST"])
@login_required
def match(summoner):
    # past number of games?
    # TODO: make better check/error handling if summoner name exists

    summoner = lol_watcher.summoner.by_name(my_region, summoner)

    try:
        response = lol_watcher.match.matchlist_by_puuid(my_region, summoner["puuid"])
    except ApiError as err:
        if err.response.status_code == 429:
            print("We should retry in {} seconds.".format(err.headers["Retry-After"]))
            print("this retry-after is handled by default by the RiotWatcher library")
            print("future requests wait until the retry-after time passes")
        elif err.response.status_code == 404:
            print("Summoner with that ridiculous name not found.")
        else:
            raise

    res = lol_watcher.match.by_id(my_region, response[0])
    game_info = {}

    # gameDuration is just the total num of seconds
    minutes = int(res["info"]["gameDuration"] / 60)
    seconds = res["info"]["gameDuration"] % 60
    game_info["gameDuration"] = f"{minutes}:{seconds}"
    game_info["gameMode"] = res["info"]["gameMode"]
    game_info["gameId"] = res["info"]["gameId"]
    participants = res["info"]["participants"]

    averages = {}
    total_gold = 0
    total_damage = 0
    for participant in participants:
        total_gold = int(participant["goldEarned"] + total_gold)
        total_damage = int(participant["totalDamageDealt"] + total_damage)

    averages["gold"] = total_gold / len(participants)
    averages["total_damage"] = total_damage / len(participants)

    for participant in participants:
        participant["plot_data"] = create_plot_for_participant(participant, averages)

    return render_template(
        "match.html",
        participants=participants,
        game_info=game_info,
        user=current_user,
        summoner=summoner["name"],
    )


@views.route("/league-form", methods=["GET", "POST"])
@login_required
def league_form():
    if request.method == "POST":
        summonerName = request.form.get("summoner")
        if not summonerName:
            flash("Please enter a valid summoner", category="error")
        else:
            return redirect(url_for("views.match", summoner=summonerName))

    return render_template("league_form.html", user=current_user)


@views.route("/my-fortnite-account/", defaults={"id": 1})
@views.route("/my-fortnite-account/<string:player>", methods=["GET", "POST"])
@login_required
def my_fortnite_account(player):
    player_stats = fort_api.stats.fetch_by_name(name=player)

    # get more info for summoner
    return render_template(
        "my_fortnite_account.html",
        user=current_user,
        player_stats=player_stats.raw_data,
    )


@views.route("/my-league-account/", defaults={"id": 1})
@views.route("/my-league-account/<string:summoner>", methods=["GET", "POST"])
@login_required
def my_league_account(summoner):
    summonerInfo = lol_watcher.summoner.by_name(my_region, summoner)

    # get more info for summoner
    return render_template(
        "my_league_account.html",
        user=current_user,
        summonerInfo=summonerInfo,
    )


@views.route("/fortnite-match/", defaults={"id": 1})
@views.route("/fortnite-match/<string:player>", methods=["GET", "POST"])
@login_required
def fortnite_match(player):
    # past number of games?
    # TODO: make better check/error handling if summoner name exists

    player_stats = fort_api.stats.fetch_by_name(name=player)

    return render_template(
        "fortnite_match.html",
        players=[],
        user=current_user,
        player=player,
        stats=player_stats.raw_data,
    )


@views.route("/fortnite-form", methods=["GET", "POST"])
@login_required
def fortnite_form():
    if request.method == "POST":
        playerName = request.form.get("player")
        if not playerName:
            flash("Please enter a valid player", category="error")
        else:
            return redirect(url_for("views.fortnite_match", player=playerName))

    return render_template("fortnite_form.html", user=current_user)


def create_plot_for_participant(participant, averages):
    # TODO: make a better plot with matplotlib, bokeh, or seaborn
    plot.close()
    x = [
        "avg gold",
        participant["summonerName"] + " gold",
        "avg damage",
        participant["summonerName"] + " damage",
    ]
    data = [
        averages["gold"],
        participant["goldEarned"],
        averages["total_damage"],
        participant["totalDamageDealt"],
    ]
    plot.bar(x, data)

    for idx, value in enumerate(data):
        plot.text(idx, value + 100, str(int(value)))

    img = io.BytesIO()
    plot.savefig(img, format="png")
    img.seek(0)
    participant["plot_data"] = urllib.parse.quote(
        base64.b64encode(img.getvalue()).decode("utf-8")
    )
    plot_data = urllib.parse.quote(base64.b64encode(img.getvalue()).decode("utf-8"))

    return plot_data
