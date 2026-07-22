import os
import random
import sqlite3
import discord
from discord import app_commands
from dotenv import load_dotenv

# .env 파일에서 토큰 불러오기
load_dotenv()

OWNER_ID = int(os.getenv("OWNER_ID"))
YOUR_SERVER_ID = int(os.getenv("YOUR_SERVER_ID"))
BOT_TOKEN = os.getenv("BOT_TOKEN")

TARGET_CHANNEL_ID = (
    1529496156608925756  # 예: 봇이 말하게 할 채널의 ID 숫자 입력
)

conn = sqlite3.connect("dictionary.db")
cursor = conn.cursor()
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS words
    (
        id
        INTEGER
        PRIMARY
        KEY
        AUTOINCREMENT,
        keyword
        TEXT,
        answer
        TEXT,
        author
        TEXT,
        status
        INTEGER
        DEFAULT
        0,
        forham
        INTEGER
        DEFAULT
        0
    )
    """
)
conn.commit()
conn.close()


class DeleteSelectView(discord.ui.View):

    def __init__(self, rows):
        super().__init__(timeout=60)

        options = []
        for row in rows:
            idx, kw, ans, author, status, forham = row
            status_str = "승인됨" if status == 1 else "대기중"
            forham_str = "포함" if forham == 1 else "정확히"
            label = f"ID: {idx} | 키워드: {kw}"
            desc = f"답변: {ans[:30]}... ({author}, {status_str}, {forham_str})"

            options.append(
                discord.SelectOption(
                    label=label[:100], value=str(idx), description=desc[:100]
                )
            )

        self.select_item = discord.ui.Select(
            placeholder="삭제할 항목을 선택하세요...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.select_item.callback = self.select_callback
        self.add_item(self.select_item)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "❌ 이 봇의 제작자만 사용할 수 있습니다.", ephemeral=True
            )
            return

        selected_id = int(self.select_item.values[0])

        conn = sqlite3.connect("dictionary.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT keyword, answer FROM words WHERE id = ?", (selected_id,)
        )
        row = cursor.fetchone()

        if row:
            cursor.execute("DELETE FROM words WHERE id = ?", (selected_id,))
            conn.commit()
            conn.close()

            await interaction.response.edit_message(
                content=f"🗑️ ID **{selected_id}**번 (`{row[0]}` -> `{row[1]}`) 항목이 성공적으로 삭제되었습니다!",
                embed=None,
                view=None,
            )
        else:
            conn.close()
            await interaction.response.edit_message(
                content="❌ 이미 삭제되었거나 존재하지 않는 항목입니다.",
                embed=None,
                view=None,
            )


# 봇 클라이언트 설정
class MyBot(discord.Client):

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        MY_GUILD = discord.Object(id=YOUR_SERVER_ID)

        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)
        print("해당 서버에 슬래시 명령어가 즉시 동기화되었습니다.")


bot = MyBot()


@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user.name} (ID: {bot.user.id})")
    print("----------------------------------")


# /가르치기 명령어
@bot.tree.command(
    name="가르치기",
    description="봇에게 새로운 단어와 답변을 가르칩니다. (관리자 승인 후 반영)",
)
@app_commands.describe(keyword="질문이나 키워드", answer="봇이 대답할 내용")
async def teach(
        interaction: discord.Interaction, keyword: str, answer: str
):
    conn = sqlite3.connect("dictionary.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO words (keyword, answer, author, status, forham) VALUES (?,"
        " ?, ?, 0, 0)",
        (keyword, answer, str(interaction.user)),
    )
    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"📝 **[{keyword}]**에 대한 가르침이 접수되었습니다! 관리자의 승인을 기다리는 중입니다.",
        ephemeral=True,
    )


# /대기목록 명령어
@bot.tree.command(
    name="대기목록", description="[제작자용] 승인을 기다리는 단어 목록을 확인합니다."
)
async def pending_list(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ 이 명령어는 봇 제작자만 사용할 수 있습니다.", ephemeral=True
        )
        return

    conn = sqlite3.connect("dictionary.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, keyword, answer, author FROM words WHERE status = 0")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message(
            "현재 승인 대기 중인 단어가 없습니다.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="📋 승인 대기 중인 단어 목록", color=discord.Color.yellow()
    )
    for row in rows:
        idx, kw, ans, author = row
        embed.add_field(
            name=f"ID: {idx} | 키워드: {kw}",
            value=f"답변: {ans}\n제안자: {author}",
            inline=False,
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# 5. /승인 명령어 (제작자 전용)
@bot.tree.command(
    name="승인",
    description="[제작자용] ID에 해당하는 단어를 승인하여 봇에 반영합니다.",
)
@app_commands.describe(word_id="승인할 단어의 ID 번호")
async def approve(interaction: discord.Interaction, word_id: int):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ 이 명령어는 봇 제작자만 사용할 수 있습니다.", ephemeral=True
        )
        return

    conn = sqlite3.connect("dictionary.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT keyword, answer FROM words WHERE id = ? AND status = 0",
        (word_id,),
    )
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE words SET status = 1 WHERE id = ?", (word_id,))
        conn.commit()
        conn.close()
        await interaction.response.send_message(
            f"✅ ID {word_id}번 ('{row[0]}')이 승인되었습니다! 이제 봇이 이 답변을 말합니다."
        )
    else:
        conn.close()
        await interaction.response.send_message(
            f"❌ ID {word_id}번에 해당하는 대기 중인 단어를 찾을 수 없습니다.",
            ephemeral=True,
        )


# 6. /삭제 명령어 (제작자 전용)
@bot.tree.command(
    name="삭제",
    description="[제작자용] 특정 단어에 등록된 내용들을 확인하고 선택해서 삭제합니다.",
)
@app_commands.describe(keyword="삭제할 질문/키워드")
async def delete_word(interaction: discord.Interaction, keyword: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ 이 명령어는 봇 제작자만 사용할 수 있습니다.", ephemeral=True
        )
        return

    conn = sqlite3.connect("dictionary.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, keyword, answer, author, status, forham FROM words WHERE keyword = ?",
        (keyword,),
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message(
            f"❌ '{keyword}' 키워드로 등록된 데이터가 없습니다.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"🗑️ '{keyword}' 삭제 관리",
        description="아래 목록에서 삭제할 항목을 선택해 주세요.",
        color=discord.Color.red(),
    )
    for row in rows:
        idx, kw, ans, author, status, forham = row
        status_str = "🟢 승인됨" if status == 1 else "🟡 대기중"
        forham_str = "🔍 포함(1)" if forham == 1 else "🎯 정확히(0)"
        embed.add_field(
            name=f"ID: {idx} ({status_str} / {forham_str})",
            value=f"답변: {ans}\n제안자: {author}",
            inline=False,
        )

    view = DeleteSelectView(rows)

    await interaction.response.send_message(
        embed=embed, view=view, ephemeral=True
    )


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 만약 지정한 특정 채널이 아니라면 무시하고 리턴 (아예 반응 안 함)
    if message.channel.id != TARGET_CHANNEL_ID:
        return

    content = message.content.strip()

    conn = sqlite3.connect("dictionary.db")
    cursor = conn.cursor()

    # 1. status = 1 이면서, forham = 0 인 것 중 '정확히 일치'하는 것 찾기
    cursor.execute(
        "SELECT answer FROM words WHERE keyword = ? AND status = 1 AND forham = 0",
        (content,),
    )
    exact_rows = cursor.fetchall()

    # 2. status = 1 이면서, forham = 1 인 것 중 문장에 '포함'되어 있는 것 찾기
    cursor.execute(
        "SELECT answer FROM words WHERE ? LIKE '%' || keyword || '%' AND status ="
        " 1 AND forham = 1",
        (content,),
    )
    include_rows = cursor.fetchall()

    conn.close()

    # 두 결과 합치기
    all_rows = exact_rows + include_rows

    if all_rows:
        selected_answer = random.choice(all_rows)[0]
        await message.channel.send(selected_answer)


# 봇 실행
bot.run(BOT_TOKEN)
