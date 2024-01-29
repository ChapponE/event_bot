import settings
import discord
from discord.ext import commands, tasks
from discord_events_class import DiscordEvents
from datetime import datetime, timedelta
import pytz
import asyncio

# Constants
DAY = 6  # The day on which the weekly reminder is triggered (0 is Monday, 6 is Sunday)
HOUR = 12  # The hour (UTC) at which the weekly reminder is triggered
MIN_MIN = 20  # The minimum minute within the HOUR for the weekly reminder
MIN_MAX = 40  # The maximum minute within the HOUR for the weekly reminder
DAYS_INTERVAL = 7  # The number of days into the future for considering events
NB_MINUTES_LIST_EVENTS_SLEEP = MIN_MAX - MIN_MIN + 1  # Interval to sleep after posting events in the channel
NB_MINUTES_WEEKLY_REMINDER_LOOP = MIN_MAX - MIN_MIN - 1  # Interval for the weekly reminder loop
NB_MINUTES_CHECK_CHANGES_LOOP = 20  # Interval to check for changes in events

# Global variables
last_message_id = None
time_events_announced = None
event_txt_time_id = None
weekly_reminder_is_sleeping = False

# Logger setup
logger = settings.logging.getLogger("bot")

# Messages
intro_txt = "Bonjour à tous ! Voici les événements de cette fin de semaine au ZincADit, n'hésitez pas à venir bénévoler ❤️ :\n \n"
no_event = "Il n'y a pas encore d'événement programmé dans les prochains jours."

def run():
    # Initialize Discord bot
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    # Define scheduled tasks
    @tasks.loop(minutes=NB_MINUTES_WEEKLY_REMINDER_LOOP)
    async def weekly_reminder():
        # Trigger weekly reminder if conditions are met
        now = datetime.now(pytz.utc)
        if now.weekday() == DAY and now.hour + 1 == HOUR and MIN_MIN <= now.minute <= MIN_MAX:
            await list_events()

    @tasks.loop(minutes=NB_MINUTES_CHECK_CHANGES_LOOP)
    async def check_changes():
        # Check for changes and update events accordingly
        global last_message_id
        global event_txt_time_id
        global weekly_reminder_is_sleeping

        if last_message_id:
            channel = bot.get_channel(int(settings.CHANNEL_ID))
            last_message = await channel.fetch_message(last_message_id)
            last_message_txt = last_message.content
            list_futur_message, events = await oncoming_event_list(time_events_announced)

            part_message_futur = "\n\n".join(list_futur_message)
            now = datetime.now(pytz.utc)

            # Check conditions for updates
            if part_message_futur == last_message_txt[-len(part_message_futur):]: #or weekly_reminder_is_sleeping:
                # If part_msg is in last_message or we are close to the DAY, HOUR set, don't do anything
                pass
            else:
                event_txt_time_id_updated = await list_events_updated(time_events_announced, events)
                all_events_passed = all(datetime.fromisoformat(event[1][1]) <= now for event in event_txt_time_id) if event_txt_time_id != [[no_event, [None, None], None]] else True

                if not (all_events_passed and event_txt_time_id_updated == [[no_event, [None, None], None]] and event_txt_time_id != [[no_event, [None, None], None]]):
                    event_txt_ordered = await order_events(event_txt_time_id_updated)
                    modified_text_message = await list_to_message(event_txt_ordered)
                    await last_message.edit(content=modified_text_message)

    @bot.event
    async def on_ready():
        # Actions to be taken when the bot is ready
        logger.info(f"User: {bot.user} (ID: {bot.user.id})")
        logger.info("Weekly reminder and check changes tasks started.")
        weekly_reminder.start()
        check_changes.start()
        print("__________________")

    @bot.event
    async def on_command_error(ctx, error):
        # Handle errors globally
        if isinstance(error, commands.MissingRequiredArgument):
            logger.error("Handled error globally")

    async def oncoming_event_list(time_events_announced):
        # Fetch upcoming events
        discord_events = DiscordEvents(settings.DISCORD_API_SECRET)
        events = await discord_events.list_guild_events(int(settings.GUILD_ID))

        if events:
            # Filter events based on scheduled start time
            filtered_events = [event for event in events if datetime.fromisoformat(event['scheduled_start_time']) <= time_events_announced]
            filtered_events_futur = [event for event in events if datetime.fromisoformat(event['scheduled_start_time']) > time_events_announced]

            for event in filtered_events_futur:
                if event in event_txt_time_id:
                    filtered_events = []

            if filtered_events:
                # Sort events based on start time
                filtered_events.sort(key=lambda x: x['scheduled_start_time'] if x['scheduled_start_time'] else datetime.max)
                events_name = [f"**{event['name']}**" for event in filtered_events]
                events_date = await asyncio.gather(*[convert_date(event['scheduled_start_time']) for event in filtered_events]) + len(filtered_events)*["\n"]
                events_description = [f"{event['description']}" for event in filtered_events]
                events_txt = [events_name[i] + "\n" + f"**{events_date[i]}**" + "\n" + events_description[i] for i in range(len(filtered_events))]

                return events_txt, filtered_events
            else:
                return [no_event], None
        else:
            return [no_event], None

    async def order_events(event_txt_time_id_updated):
        # Order events based on scheduled start time
        global event_txt_time_id

        if event_txt_time_id != [[no_event, [None, None], None]]:
            event_txt_time_id_previous_message = event_txt_time_id.copy()
            event_txt_time_id_passed = [event for event in event_txt_time_id_previous_message if datetime.fromisoformat(event[1][0]) <= datetime.now(pytz.utc)]

            if event_txt_time_id_updated != [[no_event, [None, None], None]]:
                event_txt_time_id_changed = [event for event in event_txt_time_id_updated if event not in event_txt_time_id_passed and event not in event_txt_time_id_previous_message]
                event_txt_time_id_not_changed = [event for event in event_txt_time_id_updated if event not in event_txt_time_id_passed and event in event_txt_time_id_previous_message]
                all_events = event_txt_time_id_passed + event_txt_time_id_not_changed + event_txt_time_id_changed
            else:
                if event_txt_time_id_passed:
                    all_events = event_txt_time_id_passed
                else:
                    all_events = [[no_event, [None, None], None]]
        else:
            if event_txt_time_id_updated != [[no_event, [None, None], None]]:
                event_txt_time_id_changed = [event for event in event_txt_time_id_updated]
                all_events = event_txt_time_id_changed
            else:
                all_events = [[no_event, [None, None], None]]

        if all_events != [[no_event, [None, None], None]]:
            all_events.sort(key=lambda x: x[1][0] if x[1][0] else datetime.max)

        event_txt_time_id = all_events
        ordered_event_texts = [event[0] for event in all_events]

        return ordered_event_texts

    async def list_events_updated(time_events_announced, events):
        # Update event list based on changes
        try:
            if events:
                filtered_events = [event for event in events if datetime.fromisoformat(event['scheduled_start_time']) <= time_events_announced]

                if filtered_events:
                    event_name_updated = [f"**{event['name']}**" for event in filtered_events]
                    events_date_updated = await asyncio.gather(*[convert_date(event['scheduled_start_time']) for event in filtered_events]) + len(filtered_events)*["\n"]
                    events_description_updated = [f"{event['description']}" for event in filtered_events]
                    events_txt_updated = [event_name_updated[i] + "\n" + f"**{events_date_updated[i]}**" + "\n" + events_description_updated[i] for i in range(len(filtered_events))]
                    events_time_updated = [[event['scheduled_start_time'], event['scheduled_end_time']] for event in filtered_events]
                    events_id_updated = [event['id'] for event in filtered_events]
                    event_txt_time_id_updated = [[events_txt_updated[i], [events_time_updated[i][0], events_time_updated[i][1]], events_id_updated[i]] for i in range(len(filtered_events))]

                    return event_txt_time_id_updated
                else:
                    event_txt_time_id_updated = [[no_event, [None, None], None]]
                    return event_txt_time_id_updated
            else:
                event_txt_time_id_updated = [[no_event, [None, None], None]]
                return event_txt_time_id_updated
        except Exception as e:
            logger.error(f"An error occurred: {e}")

    async def list_to_message(event_txt_ordered):
        # Convert event list to formatted message
        if event_txt_ordered != [no_event]:
            return f"{intro_txt}" + "\n\n".join(event_txt_ordered)
        else:
            return no_event

    async def convert_date(date):
        # Convert date to localized and formatted string
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
        # List upcoming events and post in Discord channel
        global last_message_id
        global time_events_announced
        global event_txt_time_id
        global weekly_reminder_is_sleeping

        discord_events = DiscordEvents(settings.DISCORD_API_SECRET)
        channel = bot.get_channel(int(settings.CHANNEL_ID))
        weekly_reminder_is_sleeping = True
        events = await discord_events.list_guild_events(int(settings.GUILD_ID))

        if events:
            current_time = datetime.now(pytz.utc)
            time_events_announced = current_time + timedelta(days=DAYS_INTERVAL)
            filtered_events = [event for event in events if datetime.fromisoformat(event['scheduled_start_time']) <= time_events_announced]
            filtered_events.sort(key=lambda x: x['scheduled_start_time'] if x['scheduled_start_time'] else datetime.max)

            if filtered_events:
                events_name = [f"**{event['name']}**" for event in filtered_events]
                events_date = await asyncio.gather(*[convert_date(event['scheduled_start_time']) for event in filtered_events]) + len(filtered_events)*["\n"]
                events_description = [f"{event['description']}" for event in filtered_events]
                events_txt = [events_name[i] + "\n" + f"**{events_date[i]}**" + "\n" + events_description[i] for i in range(len(filtered_events))]
                events_time = [[event['scheduled_start_time'], event['scheduled_end_time']] for event in filtered_events]
                events_id = [event['id'] for event in filtered_events]
                event_txt_time_id = [[events_txt[i], [events_time[i][0], events_time[i][1]], events_id[i]] for i in range(len(filtered_events))]

                message = await channel.send(f"{intro_txt}" + "\n\n".join(events_txt))
                last_message_id = message.id

                await asyncio.sleep(60*NB_MINUTES_LIST_EVENTS_SLEEP)
                weekly_reminder_is_sleeping = False
            else:
                message = await channel.send(no_event)
                last_message_id = message.id
                event_txt_time_id = [[no_event, [None, None], None]]
                await asyncio.sleep(60*NB_MINUTES_LIST_EVENTS_SLEEP)
                weekly_reminder_is_sleeping = False
        else:
            message = await channel.send(no_event)
            last_message_id = message.id
            event_txt_time_id = [[no_event, [None, None], None]]
            await asyncio.sleep(60*NB_MINUTES_LIST_EVENTS_SLEEP)
            weekly_reminder_is_sleeping = False

    bot.run(settings.DISCORD_API_SECRET, root_logger=True)

if __name__ == "__main__":
    run()
