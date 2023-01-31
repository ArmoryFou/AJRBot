import asyncio
import csv
from datetime import datetime, timedelta
import discord

import matplotlib.pyplot as plt
import numpy as np

from helpers.general import intToWeekday, send_error_message


MONTHS = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
          "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

MEDIA_TYPES = {"LIBRO", "MANGA", "VN", "ANIME",
               "LECTURA", "TIEMPOLECTURA", "AUDIO", "VIDEO"}

MEDIA_TYPES_ENGLISH = {"BOOK": "LIBRO", "READING": "LECTURA",
                       "READTIME": "TIEMPOLECTURA", "LISTENING": "AUDIO"}

TIMESTAMP_TYPES = {"TOTAL", "MES", "SEMANA", "HOY"}


def get_media_element(num, media):
    if media in {"MANGA", "LIBRO"}:
        if int(num) == 1:
            return "1 página"
        return f"{num} páginas"
    if media in {"VN", "LECTURA"}:
        if int(num) == 1:
            return "1 caracter"
        return f"{num} caracteres"
    if media == "ANIME":
        if int(num) == 1:
            return "1 episodio"
        return f"{num} episodios"
    if media in {"TIEMPOLECTURA", "AUDIO", "VIDEO"}:
        if int(num) < 60:
            return f"{int(num)%60} minutos"
        elif int(num) < 120:
            return f"1 hora y {int(num)%60} minutos"
        return f"{int(int(num)/60)} horas y {int(num)%60} minutos"


def calc_media(points):
    # Mejor prevenir que curar
    result = {
        "libro": points,
        "manga": points * 5,
        "vn": points * 350,
        "anime": points / 95 * 10,
        "lectura": points * 350,
        "tiempolectura": points / 45 * 100,
        "audio": points / 45 * 100,
        "video": points / 45 * 100
    }
    return result


def get_ranking_title(timelapse, media):
    tiempo = ""
    if timelapse == "MES":
        tiempo = "mensual"
    elif timelapse == "SEMANA":
        tiempo = "semanal"
    elif timelapse == "HOY":
        tiempo = "diario"
    elif timelapse.isnumeric():
        tiempo = "de " + timelapse
    else:
        tiempo = "total"
    medio = ""
    if media in {"MANGA", "ANIME", "AUDIO", "LECTURA", "VIDEO"}:
        medio = "de " + media.lower() + " "
    elif media in {"LIBRO"}:
        medio = "de " + media.lower() + "s "
    elif media in {"LECTURATIEMPO"}:
        medio = "de lectura (tiempo) "
    elif media in {"VN"}:
        medio = "de " + media + " "
    return f"{tiempo} {medio}"


async def add_log(db, userid, log, username):
    users = db.users
    user = users.find_one({'userId': userid})
    newid = len(user["logs"])
    log["id"] = user["lastlog"] + 1
    users.update_one(
        {'userId': userid},
        {'$push': {"logs": log},
         '$set': {"lastlog": log["id"], "username": username}}
    )
    return log["id"]


async def get_user_logs(db, userid, timelapse, media=None):
    users = db.users

    if timelapse in MONTHS:
        year = datetime.now().year
        month = MONTHS.index(timelapse) + 1
        timelapse = f"{year}/{month}"

    if timelapse == "TOTAL":
        if media in MEDIA_TYPES:
            # ALL LOGS OF A MEDIA TYPE FROM USER
            result = users.aggregate([
                {
                    "$match": {
                        "userId": userid
                    }
                }, {
                    "$project": {
                        "logs": {
                            "$filter": {
                                "input": "$logs",
                                "as": "log",
                                "cond": {"$eq": ["$$log.medio", media]}
                            }
                        }
                    }
                }
            ])
            if result:
                for elem in result:
                    # Only one document should be found so no problem returning data
                    return elem["logs"]
        else:
            # ALL LOGS OF ALL MEDIA TYPES FROM USER
            result = users.find_one({"userId": userid}, {"logs"})
            if result:
                return result["logs"]
        return ""

    if timelapse == "SEMANA":
        start = int((datetime.today() - timedelta(weeks=1)
                     ).replace(hour=0, minute=0, second=0).timestamp())
        end = int(datetime.today().replace(
            hour=23, minute=59, second=59).timestamp())
        # SEVEN-DAY LOGS OF A MEDIA TYPE FROM USER

    elif timelapse == "MES":
        start = int(
            (datetime(datetime.today().year, datetime.today().month, 1)).replace(hour=0, minute=0, second=0).timestamp())
        end = int(datetime.today().replace(
            hour=23, minute=59, second=59).timestamp())

    elif timelapse == "HOY":
        start = int(datetime.today().replace(
            hour=0, minute=0, second=0).timestamp())
        end = int(datetime.today().replace(
            hour=23, minute=59, second=59).timestamp())
    else:
        split_time = timelapse.split("/")
        if len(split_time) == 1:
            # TOTAL VIEW
            start = int(
                (datetime(int(split_time[0]), 1, 1)).replace(hour=0, minute=0, second=0).timestamp())
            end = int(
                (datetime(int(split_time[0]), 12, 31)).replace(hour=23, minute=59, second=59).timestamp())

        elif len(split_time) == 2:
            # MONTHLY VIEW
            month = int(split_time[1])
            year = int(split_time[0])
            start = int(
                (datetime(int(year), month, 1)).replace(hour=0, minute=0, second=0).timestamp())
            if month + 1 > 12:
                month = 0
                year += 1
            end = int(
                (datetime(int(year), month + 1, 1) - timedelta(days=1)).replace(hour=23, minute=59, second=59).timestamp())
        else:
            day = int(split_time[2])
            month = int(split_time[1])
            year = int(split_time[0])
            start = int((datetime(int(year), month, 1)).replace(
                hour=0, minute=0, second=0).timestamp())
            end = int((datetime(int(year), month, day)).replace(
                hour=23, minute=59, second=59).timestamp())
    query = [{"$match": {"userId": userid}},
             {
        "$project": {
            "logs": {
                "$filter": {
                    "input": "$logs",
                    "as": "log",
                    "cond": {"$and": [
                            {"$gte": ["$$log.timestamp", start]},
                            {"$lte": ["$$log.timestamp", end]}
                    ]}
                }
            }
        }
    }]
    if media in MEDIA_TYPES:
        query[1]["$project"]["logs"]["$filter"]["cond"]["$and"].append(
            {"$eq": ["$$log.medio", media]})
    result = users.aggregate(query)
    if result:
        for elem in result:
            # Only one document should be found so no problem returning data
            return elem["logs"]
    return ""


async def get_total_immersion_of_month(db, timelapse):
    users = db.users
    split_time = timelapse.split("/")
    month = int(split_time[1])
    year = int(split_time[0])
    start = int(
        (datetime(int(year), month, 1)).replace(hour=0, minute=0, second=0).timestamp())
    if month + 1 > 12:
        month = 0
        year += 1
    end = int(
        (datetime(int(year), month + 1, 1) - timedelta(days=1)).replace(hour=23, minute=59, second=59).timestamp())
    query = [{
        "$project": {
            "logs": {
                "$filter": {
                    "input": "$logs",
                    "as": "log",
                    "cond": {"$and": [
                            {"$gte": ["$$log.timestamp", start]},
                            {"$lte": ["$$log.timestamp", end]}
                    ]}
                }
            }
        }
    }]
    result = users.aggregate(query)
    total = 0
    if result:
        for elem in result:
            # Only one document should be found so no problem returning data
            for log in elem["logs"]:
                total += log["puntos"]

    return total


async def get_total_parameter_of_media(db, media, userid):
    users = db.users
    # ALL LOGS OF A MEDIA TYPE FROM USER
    logs = await get_user_logs(db, userid, "TOTAL")
    total_param = 0
    for log in logs:
        if log["medio"] == media:
            total_param += int(log["parametro"])
    return total_param


async def remove_log(db, userid, logid):
    users = db.users
    result = users.update_one(
        {"userId": userid}, {"$pull": {"logs": {"id": int(logid)}}})
    return result.modified_count


async def remove_last_log(db, userid):
    users = db.users
    result = users.update_one(
        {"userId": userid}, {"$pop": {"logs": 1}})
    return result.modified_count


async def get_user_data(db, userid, timelapse, media="TOTAL"):
    logs = await get_user_logs(db, userid, timelapse, media)
    points = {
        "LIBRO": 0,
        "MANGA": 0,
        "ANIME": 0,
        "VN": 0,
        "LECTURA": 0,
        "TIEMPOLECTURA": 0,
        "AUDIO": 0,
        "VIDEO": 0,
        "TOTAL": 0
    }
    parameters = {
        "LIBRO": 0,
        "MANGA": 0,
        "ANIME": 0,
        "VN": 0,
        "LECTURA": 0,
        "TIEMPOLECTURA": 0,
        "AUDIO": 0,
        "VIDEO": 0,
        "TOTAL": 0
    }

    for log in logs:
        points[log["medio"]] += log["puntos"]
        parameters[log["medio"]] += int(log["parametro"])
        points["TOTAL"] += log["puntos"]
    return points, parameters


async def get_best_user_of_range(db, media, timelapse):
    aux = None
    users = db.users.find({}, {"userId", "username"})
    points = 0
    for user in users:
        userpoints, parameters = await get_user_data(db, user["userId"], timelapse, media)
        newuser = {
            "id": user["userId"],
            "username": user["username"],
            "points": round(userpoints[media], 2),
            "parameters": parameters[media]
        }
        if newuser["points"] > points:
            points = round(newuser["points"], 2)
            parameternum = newuser["parameters"]
            aux = newuser
    if not (aux is None):
        return aux
    return None


async def get_sorted_ranking(db, timelapse, media):
    leaderboard = []
    users = db.users.find({}, {"userId", "username"})
    counter = 0
    for user in users:
        points, parameters = await get_user_data(
            db, user["userId"], timelapse, media)
        leaderboard.append({
            "username": user["username"],
            "points": points["TOTAL"]})
        if media in MEDIA_TYPES:
            leaderboard[counter]["param"] = parameters[media]
        counter += 1
    return sorted(
        leaderboard, key=lambda x: x["points"], reverse=True)


async def check_user(db, userid):
    users = db.users
    return users.count_documents({'userId': userid}) > 0


async def create_user(db, userid, username):
    users = db.users
    newuser = {
        'userId': userid,
        'username': username,
        'logs': [],
        'lastlog': -1
    }
    users.insert_one(newuser)


def generate_linear_graph(points, horas):
    aux = dict(points)
    labels = []
    values = []
    for x, y in aux.items():
        labels.append(x),
        values.append(y)
    plt.plot(labels, values)
    plt.title("Inmersión en AJR")
    plt.xticks(rotation=45)
    plt.xlabel("Tiempo")
    if horas:
        plt.ylabel("Horas totales")
    else:
        plt.ylabel("Puntos totales")
    plt.fill_between(labels, values, color="#AAAAF0")
    plt.savefig("temp/image.png", bbox_inches="tight")
    plt.close()
    file = discord.File("temp/image.png", filename="image.png")
    return file


def generate_graph(points, type, timelapse=None):
    aux = dict(points)
    if type == "piechart":
        for elem in list(aux):
            if aux[elem] == 0:
                aux.pop(elem)
        aux.pop("TOTAL")

        labels = []
        values = []

        for x, y in aux.items():
            labels.append(x),
            values.append(y)

        fig1, ax1 = plt.subplots()
        ax1.pie(values, labels=labels, autopct='%1.1f%%',
                shadow=True, startangle=90, textprops={'color': "w"})
        fig1.set_facecolor("#2F3136")
        # Equal aspect ratio ensures that pie is drawn as a circle.
        ax1.axis('equal')

        plt.savefig("temp/image.png")
        plt.close()
        file = discord.File("temp/image.png", filename="image.png")
        return file
    elif type == "progress":
        labels = []
        values = []
        media = {"LIBRO": [], "LECTURA": [], "TIEMPOLECTURA": [], "ANIME": [], "MANGA": [], "VN": [],
                 "AUDIO": [], "VIDEO": []}

        for x, y in aux.items():
            labels.append(x),
            values.append(y)
        fig1, ax = plt.subplots(figsize=(10, 5))
        max = 0

        for elem in values:
            media["LIBRO"].append(elem["LIBRO"])
            media["MANGA"].append(elem["MANGA"])
            media["VN"].append(elem["VN"])
            media["ANIME"].append(elem["ANIME"])
            media["LECTURA"].append(elem["LECTURA"])
            media["TIEMPOLECTURA"].append(elem["TIEMPOLECTURA"])
            media["AUDIO"].append(elem["AUDIO"])
            media["VIDEO"].append(elem["VIDEO"])
            total = elem["LIBRO"] + elem["MANGA"] + elem["VN"] + elem["ANIME"] +  \
                elem["LECTURA"] + elem["TIEMPOLECTURA"] +  \
                elem["AUDIO"] + elem["VIDEO"]
            if total > max:
                max = total

        libro = np.array(media["LIBRO"])
        manga = np.array(media["MANGA"])
        vn = np.array(media["VN"])
        anime = np.array(media["ANIME"])
        lectura = np.array(media["LECTURA"])
        tiempolectura = np.array(media["TIEMPOLECTURA"])
        audio = np.array(media["AUDIO"])
        video = np.array(media["VIDEO"])
        plt.xticks(rotation=45)
        plt.bar(labels, libro, color='#f3554d')
        plt.bar(labels, lectura, bottom=libro, color='#f3554d')
        plt.bar(labels, tiempolectura, bottom=(
            libro + lectura), color='#f3554d')
        plt.bar(labels, anime, bottom=libro +
                lectura + tiempolectura, color='#ff88cc')
        plt.bar(labels, manga,
                bottom=libro + lectura + tiempolectura + anime, color='#4B70fB')
        plt.bar(labels, vn,
                bottom=libro + lectura + tiempolectura + anime + manga, color='#03D04B')
        plt.bar(labels, audio,
                bottom=libro + lectura + tiempolectura + anime + manga + vn, color='#FFFF44')
        plt.bar(labels, video,
                bottom=libro + lectura + tiempolectura + anime + manga + vn + audio, color='#0f5f0c')
        plt.xlabel("FECHA")
        plt.ylabel("PUNTOS")
        plt.ylim(0, max * 1.05)
        plt.legend(["LIBRO", "LECTURA", "TIEMPOLECTURA",
                    "ANIME", "MANGA", "VN", "AUDIO", "VIDEO"], loc='upper center', bbox_to_anchor=(0.5, 1.25),
                   ncol=3, fancybox=True, shadow=True, labelcolor="black")
        plt.savefig("temp/image.png", bbox_inches="tight")
        plt.close()
        file = discord.File("temp/image.png", filename="image.png")
        return file
    else:
        labels = []
        values = []
        if timelapse.upper() == "SEMANA":
            start = datetime.today().replace(hour=0, minute=0, second=0) - timedelta(days=6)
            for x in range(0, 7):
                normaldate = start + timedelta(days=x)
                auxdate = str(normaldate
                              ).replace("-", "/").split(" ")[0]
                labels.append(auxdate + intToWeekday(normaldate.weekday()))
                if auxdate in points:
                    values.append(points[auxdate])
                else:
                    values.append(0)
            plt.rc('font', family='Noto Sans CJK JP')
            fig, ax = plt.subplots()
            ax.bar(labels, values, color='#24B14D')
            ax.set_ylabel('Puntos', color="white")
            ax.tick_params(axis='both', colors='white')
            fig.set_facecolor("#2F3136")
            fig.autofmt_xdate()
            plt.savefig("temp/image.png")
            plt.close()
            file = discord.File("temp/image.png", filename="image.png")
            return file


def compute_points(log):
    # Mejor prevenir que curar
    if log["medio"] not in MEDIA_TYPES:
        return 0
    if int(log["parametro"]) > 9999999:
        return -2
    if log["medio"] == "LIBRO":
        puntos = round(int(log["parametro"]), 4)
    elif log["medio"] == "MANGA":
        puntos = round(int(log["parametro"]) / 5, 4)
    elif log["medio"] == "VN":
        puntos = round(int(log["parametro"]) / 350, 4)
    elif log["medio"] == "ANIME":
        puntos = round(int(log["parametro"]) * 95 / 10, 4)
    elif log["medio"] == "LECTURA":
        puntos = round(int(log["parametro"]) / 350, 4)
    elif log["medio"] == "TIEMPOLECTURA":
        puntos = round(int(log["parametro"]) * 45 / 100, 4)
    elif log["medio"] == "AUDIO":
        puntos = round(int(log["parametro"]) * 45 / 100, 4)
    elif log["medio"] == "VIDEO":
        puntos = round(int(log["parametro"]) * 45 / 100, 4)
    log["puntos"] = puntos
    return puntos


async def get_logs_animation(db, month, day):
    # Esta función va a tener como parámetro el día, lo pasará a la función get logs y a partir de ahí generará el ranking pertinente
    header = []
    data = []
    header.append("date")
    monthly_ranking = await get_sorted_ranking(db, MONTHS[int(month) - 1], "TOTAL")
    userlist = []
    for elem in monthly_ranking:
        if elem["points"] != 0:
            userlist.append(elem["username"])
    for user in userlist:
        header.append(user)
    total = dict()
    date = datetime.today()
    # if int(day) > date.day:
    #     day = date.day
    counter = 1
    while counter < int(day) + 1:
        total[str(counter)] = await get_sorted_ranking(
            db, f"{date.year}/{month}/{counter}", "TOTAL")
        aux = [0 for i in range(len(header))]
        aux[0] = f"{month}/{counter}/{date.year}"
        for user in total[str(counter)]:
            if user["points"] != 0:
                aux[header.index(user["username"])] = user["points"]
        counter += 1
        data.append(aux)
    with open('temp/test.csv', 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data)
    return


async def send_message_with_buttons(self, ctx, content):
    pages = len(content)
    cur_page = 1
    message = await ctx.send(f"```\n{content[cur_page-1]}\nPág {cur_page} de {pages}\n```")
    if pages > 1:
        await message.add_reaction("◀️")
        await message.add_reaction("▶️")
        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=180)
                if not user.bot:
                    # waiting for a reaction to be added - times out after x seconds, 60 in this
                    # example

                    if str(reaction.emoji) == "▶️" and cur_page != pages:
                        cur_page += 1
                        await message.edit(content=f"```{content[cur_page-1]}\nPág {cur_page} de {pages}```")
                        try:
                            await message.remove_reaction(reaction, user)
                        except discord.errors.Forbidden:
                            await send_error_message(ctx, "‼️ Los mensajes con páginas no funcionan bien en DM!")

                    elif str(reaction.emoji) == "◀️" and cur_page > 1:
                        cur_page -= 1
                        await message.edit(content=f"```{content[cur_page-1]}\nPág {cur_page} de {pages}```")
                        try:
                            await message.remove_reaction(reaction, user)
                        except discord.errors.Forbidden:
                            await send_error_message(self, ctx, "‼️ Los mensajes con páginas no funcionan bien en DM!")

                    else:
                        try:
                            await message.remove_reaction(reaction, user)
                        except discord.errors.Forbidden:
                            await send_error_message(self, ctx, "‼️ Los mensajes con páginas no funcionan bien en DM!")
                        # removes reactions if the user tries to go forward on the last page or
                        # backwards on the first page
            except asyncio.TimeoutError:
                try:
                    await message.delete()
                except discord.errors.Forbidden:
                    await send_error_message(self, ctx, "‼️ Los mensajes con páginas no funcionan bien en DM!")
                break
                # ending the loop if user doesn't react after x seconds
