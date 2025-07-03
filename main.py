import discord
from discord.ext import tasks
from discord import app_commands, client
import datetime

intents = discord.Intents.default()
intents.members = True
intents.presences = True  # Обязательно для получения статусов игроков


@client.command()
async def ping(ctx):
    await ctx.send("pong!")


class MyClient(discord.Client):

    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash команды синхронизированы!")


bot = MyClient()

# Тестовая база данных
members_data = {}
START_POINTS = 600
START_COEFF = 1
GAME_NAME = ["Grand Theft Auto V", "RAGE Multiplayer"]
LOG_CHANNEL_ID = 1390192173596676177  # Заменить на твой ID


# ---------------------------------------------------------
# Функция логов
async def log(message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"[LOG] {message}")


# ---------------------------------------------------------
# Функция для проверки, играет ли участник в нужную игру
def is_playing_game(member, game_names):
    for activity in member.activities:
        name = getattr(activity, 'name', '').lower()
        details = getattr(activity, 'details', '')
        state = getattr(activity, 'state', '')
        if any(game.lower() in name for game in game_names):
            return True, activity.name
        if details and any(game.lower() in details.lower()
                           for game in game_names):
            return True, activity.name
        if state and any(game.lower() in state.lower() for game in game_names):
            return True, activity.name
    return False, None


# ---------------------------------------------------------
# Функция обновления статуса активности и начисления очков
async def update_user_activity(member):
    if member.bot:
        return

    user = members_data.get(member.id)
    if not user:
        return

    if user.get('freeze'):
        return

    if 'vacation' in user:
        today = datetime.date.today()
        if user['vacation']['from'] <= today <= user['vacation']['to']:
            return

    is_playing, playing_game = is_playing_game(member, GAME_NAME)
    if is_playing:
        user['coeff'] += 0.025
        gained = 1 / user['coeff']
        user['points'] += gained
        await log(
            f"{member.name} играет в {playing_game} — +{gained:.2f} поинтов")
    else:
        user['coeff'] -= 0.025
        user['points'] -= 1
        await log(f"{member.name} не играет — -1 поинт")

    if user['points'] < 500:
        try:
            await member.send("Вы были исключены за низкий баланс поинтов.")
        except:
            pass
        try:
            for guild in bot.guilds:
                await guild.kick(member)
        except:
            pass
        await log(f"{member.name} был исключён за низкий баланс.")


# ---------------------------------------------------------
# Убираем обработчик on_presence_update, чтобы не проверять при каждом изменении
# @bot.event
# async def on_presence_update(before, after):
#     await update_user_activity(after)


# ---------------------------------------------------------
# Периодическая проверка активности раз в 30 минут
@tasks.loop(minutes=30)
async def check_activity():
    print("=== Запуск периодической проверки игроков ===")
    for guild in bot.guilds:
        for member in guild.members:
            await update_user_activity(member)
    print("=== Проверка завершена ===")


# ---------------------------------------------------------
# Слэш команды
@bot.tree.command(name="addmember", description="Добавить участника")
@app_commands.describe(member="Участник")
async def addmember(interaction: discord.Interaction, member: discord.Member):
    members_data[member.id] = {
        'points': START_POINTS,
        'coeff': START_COEFF,
        'freeze': False
    }
    await interaction.response.send_message(
        f"{member.name} добавлен с {START_POINTS} поинтами")
    await log(f"{member.name} добавлен.")


@bot.tree.command(name="remove", description="Удалить участника")
@app_commands.describe(member="Участник")
async def remove(interaction: discord.Interaction, member: discord.Member):
    if member.id in members_data:
        del members_data[member.id]
        await interaction.response.send_message(f"{member.name} удалён.")
        await log(f"{member.name} удалён.")


@bot.tree.command(name="checkpoint",
                  description="Посмотреть количество поинтов у участника")
@app_commands.describe(
    member="Участник (если не указать, покажет ваши поинты)")
async def checkpoint(interaction: discord.Interaction,
                     member: discord.Member = None):
    target = member or interaction.user
    user_data = members_data.get(target.id)
    if not user_data:
        await interaction.response.send_message(
            f"{target.name} не зарегистрирован!", ephemeral=True)
        return

    points = user_data['points']
    coeff = user_data['coeff']
    await interaction.response.send_message(
        f"💰 У **{target.name}** сейчас **{points:.2f}** поинтов.\n"
        f"Коэффициент: {coeff:.3f}",
        ephemeral=True)


@bot.tree.command(
    name="checkapi",
    description="Проверить, играет ли участник в GTA V или RAGE Multiplayer")
@app_commands.describe(member="Участник (если не указать, проверит вас)")
async def checkapi(interaction: discord.Interaction,
                   member: discord.Member = None):
    target = member or interaction.user

    is_playing, playing_game = is_playing_game(target, GAME_NAME)

    if is_playing:
        await interaction.response.send_message(
            f"✅ {target.name} сейчас играет в **{playing_game}**.",
            ephemeral=True)
    else:
        await interaction.response.send_message(
            f"❌ {target.name} сейчас **не играет** в GTA V или RAGE Multiplayer.",
            ephemeral=True)


@bot.tree.command(name="debugstatus", description="Показать всю активность")
@app_commands.describe(member="Участник (если не указать, проверит вас)")
async def debugstatus(interaction: discord.Interaction,
                      member: discord.Member = None):
    target = member or interaction.user
    if not target.activities:
        await interaction.response.send_message("Активностей нет!",
                                                ephemeral=True)
        return

    msg = f"Активности {target.name}:\n"
    for act in target.activities:
        msg += f"- name: {getattr(act, 'name', '')}\n"
        msg += f"  details: {getattr(act, 'details', '')}\n"
        msg += f"  state: {getattr(act, 'state', '')}\n\n"

    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="freez", description="Заморозить начисление")
async def freez(interaction: discord.Interaction):
    for user in members_data.values():
        user['freeze'] = True
    await interaction.response.send_message("Бот остановлен.")
    await log("Бот был заморожен.")


@bot.tree.command(name="nofreez", description="Возобновить начисление")
async def nofreez(interaction: discord.Interaction):
    for user in members_data.values():
        user['freeze'] = False
    await interaction.response.send_message("Бот запущен.")
    await log("Бот был разморожен.")


@bot.tree.command(name="sleep", description="Отправить участника в отпуск")
@app_commands.describe(member="Участник",
                       date_from="Начало (YYYY-MM-DD)",
                       date_to="Конец (YYYY-MM-DD)")
async def sleep(interaction: discord.Interaction, member: discord.Member,
                date_from: str, date_to: str):
    if member.id in members_data:
        members_data[member.id]['vacation'] = {
            'from': datetime.datetime.strptime(date_from, "%Y-%m-%d").date(),
            'to': datetime.datetime.strptime(date_to, "%Y-%m-%d").date()
        }
        await interaction.response.send_message(
            f"{member.name} отправлен в отпуск.")
        await log(f"{member.name} в отпуске.")


@bot.tree.command(name="addsleep", description="Вернуть участника из отпуска")
@app_commands.describe(member="Участник")
async def addsleep(interaction: discord.Interaction, member: discord.Member):
    if member.id in members_data and 'vacation' in members_data[member.id]:
        del members_data[member.id]['vacation']
        await interaction.response.send_message(
            f"{member.name} вернулся из отпуска.")
        await log(f"{member.name} вернулся из отпуска.")


@bot.tree.command(name="updatemember", description="Обновить ник участника")
@app_commands.describe(member="Участник", new_name="Новый ник")
async def updatemember(interaction: discord.Interaction,
                       member: discord.Member, new_name: str):
    await member.edit(nick=new_name)
    await interaction.response.send_message(f"Ник {member.name} обновлён.")
    await log(f"Ник {member.name} обновлён.")


@bot.tree.command(name="uppoint", description="Добавить поинты")
@app_commands.describe(member="Участник", points="Количество")
async def uppoint(interaction: discord.Interaction, member: discord.Member,
                  points: int):
    if member.id in members_data:
        members_data[member.id]['points'] += points
        await interaction.response.send_message(
            f"{points} поинтов добавлено {member.name}.")
        await log(f"{points} поинтов добавлено {member.name}.")


@bot.tree.command(name="ratio", description="Обновить коэффициент")
@app_commands.describe(mode="day или night")
async def ratio(interaction: discord.Interaction, mode: str):
    if mode == 'day':
        for user in members_data.values():
            user['coeff'] += 0.025
    elif mode == 'night':
        for user in members_data.values():
            user['coeff'] += 0.030
    await interaction.response.send_message(f"Коэффициент обновлён на {mode}.")


@bot.tree.command(name="sync", description="Синхронизировать slash команды")
async def sync(interaction: discord.Interaction):
    await bot.tree.sync()
    await interaction.response.send_message("Slash команды синхронизированы!")


# ---------------------------------------------------------
# Магазин
class ShopView(discord.ui.View):

    def __init__(self):
        super().__init__()
        self.add_item(ShopButton("1️⃣", 1, 5000))
        self.add_item(ShopButton("2️⃣", 2, 9999))
        self.add_item(ShopButton("3️⃣", 3, 3500))


class ShopButton(discord.ui.Button):

    def __init__(self, label, item, price):
        super().__init__(label=label, style=discord.ButtonStyle.green)
        self.item = item
        self.price = price

    async def callback(self, interaction: discord.Interaction):
        user = members_data.get(interaction.user.id)
        if not user:
            await interaction.response.send_message("Вы не зарегистрированы!",
                                                    ephemeral=True)
            return
        if user['points'] < self.price:
            await interaction.response.send_message("Недостаточно поинтов!",
                                                    ephemeral=True)
            return
        user['points'] -= self.price
        msg = f"Вы купили товар {self.item}, цена: {self.price}, дата: {datetime.datetime.now().strftime('%Y-%m-%d')}, остаток: {user['points']}"
        await interaction.user.send(msg)
        await log(msg)
        await interaction.response.send_message("Покупка совершена!",
                                                ephemeral=True)


@bot.tree.command(name="shopkveyt", description="Открыть магазин")
async def shopkveyt(interaction: discord.Interaction):
    embed = discord.Embed(title="Магазин")
    embed.add_field(name="1️⃣ Большая сумка", value="Цена: 5000", inline=False)
    embed.add_field(name="2️⃣ 100.000", value="Цена: 9999", inline=False)
    embed.add_field(name="3️⃣ Заряд", value="Цена: 3500", inline=False)
    await interaction.response.send_message(embed=embed,
                                            view=ShopView(),
                                            ephemeral=True)


# ---------------------------------------------------------
# Старт
@bot.event
async def on_ready():
    print(f"Бот запущен как {bot.user}")
    # Запускаем цикл проверки раз в 30 минут
    check_activity.start()


# ---------------------------------------------------------
bot.run(
    'MTM5MDA3MDc4MTgzMjIwNDM2OA.GbK1FJ.AIZYyRf_g0gLk1NAHWHQyuTwDlQ6ldJX2Bifx8')
