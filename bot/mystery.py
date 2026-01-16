import discord

MYSTERY_TITLE = "???"
MYSTERY_COLOR = discord.Color.purple()

async def mystery_send(ctx, text: str, title: str = None, *, mention: str = None, send_embed: bool = True):
    """Send a mysterious-styled message. If send_embed is True, sends an embed with the mysterious title.
    Otherwise sends plain text prefixed with a whisper.
    """
    if not title:
        title = MYSTERY_TITLE
    try:
        if send_embed:
            embed = discord.Embed(title=title, description=text, color=MYSTERY_COLOR)
            embed.set_footer(text="A whisper from the unknown")
            await ctx.send(embed=embed)
        else:
            msg = f"*A whisper:* {text}"
            if mention:
                msg = f"{mention} {msg}"
            await ctx.send(msg)
    except Exception:
        # fallback to plain send
        try:
            await ctx.send(text)
        except Exception:
            pass

def mystery_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(title=title or MYSTERY_TITLE, description=description, color=MYSTERY_COLOR)
    embed.set_footer(text="A whisper from the unknown")
    return embed
