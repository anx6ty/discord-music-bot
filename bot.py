import os
import discord
from discord.ext import commands
import wavelink
import asyncio
import datetime

# ─────────────────────────────────────────────
# CONFIGURATION (Loads securely from Railway/Env)
# ─────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
LAVALINK_HOST = os.environ.get("LAVALINK_HOST", "YOUR_ZEON_IP")
LAVALINK_PORT = int(os.environ.get("LAVALINK_PORT", 2333))
LAVALINK_PASSWORD = os.environ.get("LAVALINK_PASSWORD", "YOUR_PASSWORD")

# ─────────────────────────────────────────────
# THEME & DESIGN
# ─────────────────────────────────────────────
class Theme:
    MAIN = 0x2B2D31       # Discord Dark BG (Seamless embeds)
    SUCCESS = 0x57F287    # Green
    ERROR = 0xED4245      # Red
    ACCENT = 0x5865F2     # Blurple

    SOURCE_ICONS = {
        "youtube": "YouTube",
        "spotify": "Spotify",
        "soundcloud": "SoundCloud",
    }


def build_progress_bar(position: int, length: int, size: int = 15) -> str:
    """Creates a visual slider progress bar."""
    if length == 0:
        return "🔴 **LIVE STREAM**"
    progress = int((position / length) * size)
    bar = "▬" * progress + "🔘" + "▬" * (size - progress)
    return f"`{fmt_time(position)}` {bar} `{fmt_time(length)}`"


def fmt_time(ms: int) -> str:
    """MS to readable time."""
    if not ms:
        return "0:00"
    s = int(ms / 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def embed(desc: str, title: str = None, color: int = Theme.MAIN) -> discord.Embed:
    """Fast, clean embed generator."""
    e = discord.Embed(description=desc, color=color)
    if title:
        e.title = title
    return e


# ─────────────────────────────────────────────
# BOT SETUP
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True


class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or('$'),
            intents=intents,
            help_command=None,
            max_messages=1000
        )

    async def setup_hook(self):
        node = wavelink.Node(
            uri=f"http://{LAVALINK_HOST}:{LAVALINK_PORT}",
            password=LAVALINK_PASSWORD,
            retries=3
        )
        await wavelink.Pool.connect(nodes=[node], client=self, cache_capacity=200)


bot = MusicBot()


# ─────────────────────────────────────────────
# INTERACTIVE PLAYER CONTROLLER
# ─────────────────────────────────────────────
class Controller(discord.ui.View):
    def __init__(self, player: wavelink.Player):
        super().__init__(timeout=None)
        self.player = player
        self.update_buttons()

    def update_buttons(self):
        self.pause_btn.emoji = "▶️" if self.player.paused else "⏸️"
        self.loop_btn.style = (
            discord.ButtonStyle.success
            if self.player.queue.mode == wavelink.QueueMode.loop
            else discord.ButtonStyle.secondary
        )

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        if not itx.user.voice or itx.user.voice.channel != self.player.channel:
            await itx.response.send_message(
                embed=embed("You must be in my voice channel!", color=Theme.ERROR),
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        await itx.response.defer()
        if self.player.queue.history:
            track = self.player.queue.history[-1]
            await self.player.play(track)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.primary)
    async def pause_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        await self.player.pause(not self.player.paused)
        self.update_buttons()
        await itx.response.edit_message(view=self)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        await itx.response.defer()
        await self.player.skip(force=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def loop_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        mode = self.player.queue.mode
        self.player.queue.mode = (
            wavelink.QueueMode.loop
            if mode == wavelink.QueueMode.normal
            else wavelink.QueueMode.normal
        )
        self.update_buttons()
        await itx.response.edit_message(view=self)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        await itx.response.defer()
        await self.player.disconnect()


# ─────────────────────────────────────────────
# EVENTS
# ─────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"⚡ {bot.user} is ONLINE and Fast!")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="$help • High Speed"
        )
    )


@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    print(f"🌊 Node '{payload.node.identifier}' Ready | Session: {payload.session_id}")


@bot.event
async def on_wavelink_track_start(payload: wavelink.TrackStartEventPayload):
    player = payload.player
    if not player:
        return
    track = payload.track

    if hasattr(player, "controller_msg") and player.controller_msg:
        try:
            await player.controller_msg.delete()
        except Exception:
            pass

    e = discord.Embed(color=Theme.MAIN)
    e.set_author(
        name="NOW PLAYING",
        icon_url="https://cdn.discordapp.com/emojis/741605543046807626.gif"
    )
    e.description = f"### [{track.title}]({track.uri})\n"
    e.description += build_progress_bar(0, track.length)
    e.add_field(name="Artist", value=f"`{track.author}`", inline=True)
    e.add_field(
        name="Requested By",
        value=track.requester.mention if hasattr(track, 'requester') else "Autoplay",
        inline=True
    )
    e.add_field(name="Volume", value=f"`{player.volume}%`", inline=True)
    if track.artwork:
        e.set_thumbnail(url=track.artwork)

    view = Controller(player)
    player.controller_msg = await player.home.send(embed=e, view=view)


@bot.event
async def on_wavelink_inactive_player(player: wavelink.Player):
    await player.channel.send(embed=embed("👋 Left due to inactivity.", color=Theme.MAIN))
    await player.disconnect()


# ─────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────
@bot.command(aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    if not ctx.author.voice:
        return await ctx.reply(
            embed=embed("You need to join a voice channel first.", color=Theme.ERROR)
        )

    player: wavelink.Player = ctx.voice_client
    if not player:
        player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
    player.inactive_timeout = 180
    player.autoplay = wavelink.AutoPlayMode.partial
    player.home = ctx.channel

    tracks = await wavelink.Playable.search(query)
    if not tracks:
        return await ctx.reply(
            embed=embed(f"No results found for `{query}`.", color=Theme.ERROR)
        )

    if isinstance(tracks, wavelink.Playlist):
        for t in tracks.tracks:
            t.requester = ctx.author
        added = await player.queue.put_wait(tracks)
        await ctx.reply(
            embed=embed(
                f"📚 Queued **{added}** tracks from `{tracks.name}`.",
                color=Theme.SUCCESS
            )
        )
    else:
        track = tracks[0]
        track.requester = ctx.author
        await player.queue.put_wait(track)
        if player.playing:
            await ctx.reply(
                embed=embed(
                    f"✅ Added [{track.title}]({track.uri}) to the queue.",
                    color=Theme.SUCCESS
                )
            )

    if not player.playing:
        await player.play(player.queue.get(), volume=70)


@bot.command(aliases=["s", "next"])
async def skip(ctx: commands.Context):
    player: wavelink.Player = ctx.voice_client
    if player and player.playing:
        await player.skip(force=True)
        await ctx.message.add_reaction("⏭️")


@bot.command(aliases=["stop", "dc", "leave"])
async def disconnect(ctx: commands.Context):
    player: wavelink.Player = ctx.voice_client
    if player:
        await player.disconnect()
        await ctx.message.add_reaction("👋")


@bot.command(aliases=["ps", "resume"])
async def pause(ctx: commands.Context):
    player: wavelink.Player = ctx.voice_client
    if player:
        await player.pause(not player.paused)
        await ctx.message.add_reaction("⏯️")


@bot.command(aliases=["vol", "v"])
async def volume(ctx: commands.Context, vol: int):
    player: wavelink.Player = ctx.voice_client
    if player:
        vol = max(0, min(vol, 150))
        await player.set_volume(vol)
        await ctx.reply(embed=embed(f"🔊 Volume set to **{vol}%**", color=Theme.SUCCESS))


@bot.command(aliases=["q"])
async def queue(ctx: commands.Context):
    player: wavelink.Player = ctx.voice_client
    if not player or not player.queue:
        return await ctx.reply(embed=embed("The queue is empty.", color=Theme.MAIN))

    desc = ""
    for i, t in enumerate(list(player.queue)[:10]):
        desc += f"`{i+1}.` [{t.title[:40]}]({t.uri}) `[{fmt_time(t.length)}]`\n"

    total = len(player.queue)
    if total > 10:
        desc += f"\n*+ {total - 10} more songs...*"

    e = embed(desc, title=f"📜 Queue ({total} tracks)")
    if player.current:
        e.set_author(name=f"Now Playing: {player.current.title[:50]}")
    await ctx.reply(embed=e)


@bot.command(aliases=["np"])
async def nowplaying(ctx: commands.Context):
    player: wavelink.Player = ctx.voice_client
    if not player or not player.current:
        return await ctx.reply(embed=embed("Nothing is playing right now.", color=Theme.MAIN))

    t = player.current
    e = discord.Embed(color=Theme.MAIN)
    e.set_author(name="LIVE PROGRESS")
    e.description = f"### [{t.title}]({t.uri})\n{build_progress_bar(player.position, t.length)}"
    if t.artwork:
        e.set_thumbnail(url=t.artwork)
    await ctx.reply(embed=e, view=Controller(player))


@bot.command(aliases=["l"])
async def loop(ctx: commands.Context):
    player: wavelink.Player = ctx.voice_client
    if not player:
        return
    mode = player.queue.mode
    player.queue.mode = (
        wavelink.QueueMode.loop
        if mode == wavelink.QueueMode.normal
        else wavelink.QueueMode.normal
    )
    state = "Enabled 🔁" if player.queue.mode == wavelink.QueueMode.loop else "Disabled ➡️"
    await ctx.reply(embed=embed(f"Loop {state}", color=Theme.SUCCESS))


@bot.command(aliases=["h", "cmds"])
async def help(ctx: commands.Context):
    e = discord.Embed(color=Theme.ACCENT, title="⚡ High-Speed Music Commands")
    e.description = (
        "**🎵 Playback**\n"
        "`$play` `(p)` — Play a song/playlist/url\n"
        "`$skip` `(s)` — Skip current song\n"
        "`$pause` `(ps)` — Pause or resume\n"
        "`$disconnect` `(dc)` — Stop & leave\n\n"
        "**🔧 Utility**\n"
        "`$queue` `(q)` — View song queue\n"
        "`$nowplaying` `(np)` — Live progress bar\n"
        "`$volume` `(v)` — Adjust volume (0-150)\n"
        "`$loop` `(l)` — Toggle loop mode\n"
    )
    e.set_footer(text="Prefix: $ or @Mention • Powered by Zeon Lavalink")
    await ctx.reply(embed=e)


# ─────────────────────────────────────────────
# ERROR HANDLER
# ─────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(embed=embed("Missing arguments! Check `$help`.", color=Theme.ERROR))
    else:
        print(f"⚠️ Error: {error}")


bot.run(TOKEN)