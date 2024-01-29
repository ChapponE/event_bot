import settings
import discord
from discord.ext import commands, tasks
from discord_events_class import DiscordEvents
from datetime import datetime, timedelta
import pytz
import asyncio

day_ = 6 #Monday=0, Tuesday=1 ....
hour_ = 24
min_min = 0
min_max = 60

channel_id = 1190225680609329256

logger = settings.logging.getLogger("bot")

def run():
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    
    last_message_id = None
    time_events_anounced = None

    # Récupérer le serveur (guild) par son ID
    guild_id = 1190225680609329253 

    @tasks.loop(minutes=0.5)  # Adjust the interval based on your needs
    async def weekly_reminder():
        now = datetime.now(pytz.utc)
        print(now.weekday(), now.hour, now.minute)
        if now.weekday() == day_ and now.hour + 1 == hour_ and now.minute >= min_min and now.minute <= min_max:
            
            await list_events()
            await asyncio.sleep(60*20)

    # @tasks.loop(minutes=0.2)
    # async def check_changes(last_message_id, time_events_anounced):
    #     if last_message_id:
    #         last_message = await bot.fetch_guild(last_message_id)
    #         channel = bot.get_channel(channel_id)
    #         last_message_txt = await channel.fetch_message(last_message_id)
    #         part_message = message_to_send(guild_id, time_events_anounced)
    #         now = datetime.now(pytz.utc)

    #         if part_message in last_message_txt or (now.weekday() == day_ and now.hour + 1 > hour_- 1 and now.hour + 1 > hour_+ 1):
    #             # If part_msg is in last_message or we are close to the day_, hour_ setted don't do anything
    #             pass
    #         else:
    #             part_not_change = event_before_tomorrow()
    #             new_message = part_not_change + part_message
    #             await last_message.edit(content=new_message)

    @bot.event
    async def on_ready():
        logger.info(f"User: {bot.user} (ID: {bot.user.id})")
        weekly_reminder.start()
        check_changes.start(last_message_id, time_events_anounced)
        print("__________________")

    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Handled error globally")

    async def message_to_send(channel_id, time_events_anounced):
        discord_events = DiscordEvents(settings.DISCORD_API_SECRET)
        channel = bot.get_channel(channel_id)

        try:
            events = await discord_events.list_guild_events(guild_id)
            if events:
                
                # Filter events that are within the current period of anouncement
                filtered_events = [event for event in events if datetime.fromisoformat(event['scheduled_start_time']) <= time_events_anounced]

                if filtered_events:
                    events_name = [f"**{event['name']}**" for event in filtered_events]
                    events_date = await asyncio.gather(*[convert_date(event['scheduled_start_time']) for event in filtered_events]) + len(filtered_events)*["\n"]
                    events_description = [f"{event['description']}" for event in filtered_events]
                    events_txt = [events_name[i] + "\n"+ f"**{events_date[i]}**" + "\n" + events_description[i] for i in range(len(filtered_events)) ]
                    return events_txt 
                else:
                    return ''
        except Exception as e:
            await channel.send(f"An error occurred: {e}")

    async def event_before_tomorrow():
        ...

    async def convert_date(date):
        date_initiale = datetime.fromisoformat(date).astimezone(pytz.utc)
        date_locale = date_initiale.astimezone(pytz.timezone('Europe/Paris'))

        format_souhaite = "%A %d %B %Hh%M"
        date_formatee = date_locale.strftime(format_souhaite)[:-5]

        # Define dictionaries for months and days translations
        months_translation = {
            'January': 'janvier', 'February': 'février', 'March': 'mars',
            'April': 'avril', 'May': 'mai', 'June': 'juin',
            'July': 'juillet', 'August': 'août', 'September': 'septembre',
            'October': 'octobre', 'November': 'novembre', 'December': 'décembre'
        }

        days_translation = {
            'Monday': 'lundi', 'Tuesday': 'mardi', 'Wednesday': 'mercredi',
            'Thursday': 'jeudi', 'Friday': 'vendredi', 'Saturday': 'samedi', 'Sunday': 'dimanche'
        }

        format_souhaite = "%A %d %B %Hh%M"
        date_formatee = date_locale.strftime(format_souhaite)[:-5]

        # Replace English months and days with their French translations
        for english_month, french_month in months_translation.items():
            date_formatee = date_formatee.replace(english_month, french_month)

        for english_day, french_day in days_translation.items():
            date_formatee = date_formatee.replace(english_day, french_day)

        return date_formatee
    

    async def list_events():
        nonlocal last_message_id
        nonlocal time_events_anounced

        discord_events = DiscordEvents(settings.DISCORD_API_SECRET)
        channel = bot.get_channel(channel_id)

        try:
            events = await discord_events.list_guild_events(guild_id)
            if events:
                
                # Filter events that are within the next 11 days
                current_time = datetime.now(pytz.utc)
                time_events_anounced = current_time + timedelta(days=11)
                filtered_events = [event for event in events if datetime.fromisoformat(event['scheduled_start_time']) <= time_events_anounced][::-1]  

                if filtered_events:
                    intro_txt = "Bonjours à toustes! Voici les événements de cette fin de semaine au ZincADit, n'hésitez pas à venir bénévoler ❤️ :\n \n"
                    events_name = [f"**{event['name']}**" for event in filtered_events]
                    events_date = await asyncio.gather(*[convert_date(event['scheduled_start_time']) for event in filtered_events]) + len(filtered_events)*["\n"]
                    events_description = [f"{event['description']}" for event in filtered_events]
                    events_txt = [events_name[i] + "\n"+ f"**{events_date[i]}**" + "\n" + events_description[i] for i in range(len(filtered_events)) ]
                    await channel.send(f"{intro_txt}" + "\n\n".join(events_txt))

                else:
                    message = await channel.send("No scheduled events found.")
                    last_message_id = message.id
        except Exception as e:
            await channel.send(f"An error occurred: {e}")

    
    bot.run(settings.DISCORD_API_SECRET, root_logger=True)

if __name__ == "__main__":
    run()
