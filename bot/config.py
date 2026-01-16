# prefix

BOT_PREFIX = "."

# Ability categories (canonical names). Acceptable aliases are handled in ActionQueueCog.
# Use these in other cogs to validate or display categories.
ABILITY_CATEGORIES = [
    "Manipulation",
    "Protection",
    "Blocking",
    "Curing",
    "Information",
    "Economy",
    "Transport",
    "Communication",
    "Lethal",
    "Other",
]

# Teams (canonical short names). Use `.team #rc <name>` to assign; stored lower-cased by ActionQueueCog.
TEAMS = [
    "village",
    "sublime",
    "dark",
    "evil",
    "evils",
    "neutral",
    "shadow",
    "rk",
]

# Hex color to apply to the bot role
BOT_ROLE_COLOR = "#a0d2f3"

# .setup

SERVER_STRUCTURE = {
    "THE SHADOW REALM": [],
    "OVERSEER": ["🔵│overseer-chat", "📝│notes", "🚪│log-visits", "🌀│log-actions", "🤫│whisper-logs", "✏️│edit-and-del-logs", "🪙│logs-economy", "🚪│join-leave-logs", "🤖│commands", "🌟│highlights", "✍️│commentary"],
    "ABOUT THE GAME": ["📜│rules", "📖│mechanics", "💵│economy", "🃏│role-template", "📄│playerlist", "bot-explanation"],
    "CHATS": ["💬│off-topic", "📺│spectator-lounge", "💀│graveyard", "💭│feedback"],
    "OVERSEER RELATIONS": ["❗│announcements", "💀│death-reports", "🔴│overseer-status", "🗺│map", ],
    "CASES": ["👨‍⚖️│objection", "🫵│lawsuit"],
    "DAYCHAT": ["☀️│day-discussion", "📢│megaphone", "🗳│lynch-session-1", "🗳│lynch-session-2", "👑│leader-election", "📊│vote-count"],
    "PUBLIC CHANNELS": ["🌟│the-grand-reveal", "🎂│mario-party", "🎮│games", "🥣│cereal"],
    "PRIVATE CHANNELS": ["duplicate-this", "🛡️│shield", "🍴│utensils", "👻│ghoul", "🖇️│sync"],
    "MANORS": ["🏰│manor-1"],
    "ROLES": ["1"],
    "ALTS": [],
    "DEAD RC": [],
    "INACCESSIBLE MANORS": [],
    "OLD PCS": []
}

TOP_LEVEL_CHANNELS = [
]

DEFAULT_ROLES = [
    ("Overseer", "0000ff", True),   # Blue, admin
    ("Alive", "00dae9", False),     # Cyan
    ("Sponsor", "00eb29", False),   # Green
    ("Spectator", "ff9e00", False), # Orange
    ("Alt", "000001", False),       # Almost black
    ("Dead", "f00004", False),
    ("Defendant", "652dd5", False),
    ("Plaintiff", "f1c40f", False),
    ("Judge", "e74c3c", False),
]

ROLE_PERMISSIONS = {
    "Everyone": {
        "THE SHADOW REALM": {"view": False},
        "OVERSEER": {"view": False},
        "ABOUT THE GAME": {"view": False, "send": False},
        "CHATS": {
            "view": False,
            "exceptions": {
                "off-topic": {"view": True}
            }
        },
        "OVERSEER RELATIONS": {"view": False, "send": False},
        "CASES": {"view": False, "send": False},
        "DAYCHAT": {"view": False, "send": False},
        "PUBLIC CHANNELS": {"view": False, "send": False},
        "PRIVATE CHANNELS": {"view": False},
        "MANORS": {"view": False},
        "ROLES": {"view": False},
        "ALTS": {"view": False},
        "DEAD RC": {"view": False},
        "INACCESSIBLE MANORS": {"view": False},
        "OLD PCS": {"view": False}
    },

    "Alive": {
        "ABOUT THE GAME": {"view": True},
        "OVERSEER RELATIONS": {"view": True},
        "DAYCHAT": {"view": True},
        "PUBLIC CHANNELS": {"view": True}
    },

    "Sponsor": {
        "ABOUT THE GAME": {"view": True},
        "OVERSEER RELATIONS": {"view": True},
        "DAYCHAT": {"view": True},
        "PUBLIC CHANNELS": {"view": True}
    },

    "Spectator": {
        "THE SHADOW REALM": {"view": True},
        "ABOUT THE GAME": {"view": True},
        "CHATS": {
            "view": True,
            "exceptions": {
                "💀│graveyard": {"send": False}
            }
        },
        "OVERSEER RELATIONS": {"view": True},
        "CASES": {"view": True},
        "DAYCHAT": {"view": True},
        "PUBLIC CHANNELS": {"view": True},
        "PRIVATE CHANNELS": {"view": True, "send": False},
        "MANORS": {"view": True, "send": False},
        "ROLES": {"view": True, "send": False},
        "ALTS": {"view": True, "send": False},
        "DEAD RC": {"view": True, "send": False},
        "INACCESSIBLE MANORS": {"view": True, "send": False},
        "OLD PCS": {"view": True, "send": False}
    },

    "Alt": {
        "ABOUT THE GAME": {"view": True},
        "CHATS": {"send": False},
        "OVERSEER RELATIONS": {"view": True},
        "DAYCHAT": {"view": True, "send": False},
        "PUBLIC CHANNELS": {"view": True}
    },

    "Dead": {
        "ABOUT THE GAME": {"view": True},
        "OVERSEER RELATIONS": {"view": True},
        "DAYCHAT": {"view": True, "send": False},
        "PUBLIC CHANNELS": {"view": True}
    }
}


ROLE_PERMISSIONS_DAY = {
    "Alive": {
        "DAYCHAT": {"send": True,"exceptions": {"📊│vote-count": {"send": False}}},
        
    },
    "Sponsor": {
        "DAYCHAT": {"send": True, "exceptions": {"📊│vote-count": {"send": False}}},
    }
}
# Default shop items available globally (guild_id 0)
DEFAULT_SHOP_ITEMS = [
    {
        "name": "Broom",
        "price": 800,
        "description": "Broom any amount of messages in a channel you're in.",
    },
    {
        "name": "Shield",
        "price": 3000,
        "description": "Access to the global house map updates.",
    },
    {
        "name": "Door",
        "price": 4000,
        "description": "Gain an extra visit for the night.",
    },
    {
        "name": "Whisper",
        "price": None,
        "description": "A single-use whisper item to send a short message to another player's role channel.",
    },
    {
        "name": "Miscellaneous Other Items",
        "price": None,
        "description": "You can't buy this, it's just here to represent random other items you may have from roles and stuff.",
    },
    {
        "name": "Visit",
        "price": None,
        "description": "Used to visit other locations.",
    },
    {
        "name": "Forced Enchantment",
        "price": None,
        "description": "Enchants your visit to be forced.",
    },
    {
        "name": "Stealth Enchantment",
        "price": None,
        "description": "Enchants your visit to be stealthy.",
    },
]

# Default table items (available in the private "utensils" channel per-guild)
DEFAULT_TABLE_ITEMS = [
    {
        "name": "Fork",
        "price": 500,
        "description": "Grab a player and force them to move to a manor. Forced non-stealth visit.",
        "per_customer": None,
        "stock": None,
    },
    {
        "name": "Knife",
        "price": 5000,
        "description": "Physical - Kill a player. One purchase per customer, two in stock.",
        "per_customer": 1,
        "stock": 2,
    },
    {
        "name": "Spoon",
        "price": 1000,
        "description": "Choose three manors and rename them; move inhabitants to #cereal and control those manors.",
        "per_customer": None,
        "stock": 1,
    },
    {
        "name": "Spork",
        "price": 1500,
        "description": "Move a manor into the Public Channels category; ownership transfers.",
        "per_customer": None,
        "stock": 3,
    },
    {
        "name": "Teaspoon",
        "price": 7000,
        "description": "Find out a player's category.",
        "per_customer": 1,
        "stock": None,
    },
    {
        "name": "Plate",
        "price": 1000,
        "description": "Skip a phase (e.g. N2 -> N3 or D1 -> D2).",
        "per_customer": None,
        "stock": 1,
    },
    {
        "name": "Napkin",
        "price": 900,
        "description": "Cure a player from any blockage.",
        "per_customer": None,
        "stock": None,
    },
    {
        "name": "Forky",
        "price": 1000,
        "description": "Roleblock a player's ability (randomly selected) for one cycle.",
        "per_customer": 1,
        "stock": None,
    },
]

GIFS_DIRECTORY = {
    "day": "gifs/day",
    "night": "gifs/night",
    "rebuild": "gifs/rebuild",
    "destroy": "gifs/destroy",
    "public": "gifs/public",
    "private": "gifs/private"
}

RULES_TEXT = (
"1. You cannot copy-paste, screenshot, or share in a similar way that isn't your own words, anything related to private channels. You cannot pretend to be doing this either.\n"
"2. Using code words or encrypted messages to plan during the day with only certain players is prohibited.\n"
"3. You cannot share any kind of information with other players outside of the server. (No cheating or teaming)\n"
"4. Avoid spamming, flooding the chat (talking too much throughout the day) or sending many images. If you talk about topics, or repeatedly send GIFs or images, not related to the game in day-discussion, you will be warned.\n"
"5. You can only edit or delete messages that were just recently sent to correct a mistake. You cannot instantly delete or edit recent messages either, with the purpose of simulating this way a private chat with currently online players.\n"
"6. If you misbehave: be toxic, racist, rude to other players, or stir up drama, the host and the bot will mute you. If you continuously misbehave, you could get banned. Persistent and rude comments won't be tolerated. Sending these messages to delete them right after won't work either.\n"
"7. Homophobia, racism, sexism or any form of discrimination will face a zero-tolerance policy and will be met with a one strike rule. Extreme toxicity or harassments will also be met with the same policy.\n"
"8. If you make anyone feel uncomfortable you will be warned. If you continue, you'll be timed out, then kicked if necessary.\n"
"9. If you believe an Overseer being biased towards a player, or if you have any complaint, let **Aoren** (SV owner of Hearthside) know. If you believe anyone is breaking a rule, feel free to ping Overseer as well, or reach out to us in DM.\n"
"10. Metagaming is heavily discouraged. It is your responsibility to keep it out of the game to ensure fairness for you and other players, and we recommend to not make use of it outside of your role channel.\n"
"11. Using curses, threats, reporting, flaming or ethical suicide as a defense or excuse is unacceptable and is beyond the purpose of this game.\n"
"12. Any sorts of outside tools such as DM, bots, plugins, etc. that can give you information you shouldn't have, are strictly prohibited. Failure to follow these rules will lead to restriction or removal from the game..\n"
"13. There a lot of unspoken rules that might not be listed here, at your own discretion.... use your common sense. If you know something is not allowed that is not listed as a rule, don't do it.\n"
"14. Stay respectful."
)