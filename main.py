import asyncpraw
import discord
from discord.ext import commands, tasks
import asyncio
import os

from keep_alive import keep_alive

import time
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

subreddit_name = 'mechmarket'
keywords = ["[CA-"]
client_id = 'SdzgF6CdkGmsFBPMKHFj5A'
client_secret = os.environ['client_secret']
user_agent = 'mechMarketCAN/1.0 by osuyto'
discord_token = os.environ['DISCORD_TOKEN']

reddit = asyncpraw.Reddit(
    client_id=client_id,
    client_secret=client_secret,
    user_agent=user_agent,
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    print('We have logged in as {0.user}'.format(bot))
    # check_new_posts.start()


# @bot.event
# async def on_message(message):
#     if message.author == bot.user:
#         return

#     if message.content.startswith('$hello'):
#         await message.channel.send('Hello!')

#     if message.content == '99!':
#         channel_name = message.channel.name
#         channel_id = message.channel.id
#         await message.channel.send(
#             f'Channel Name: {channel_name}\nChannel ID: {channel_id}')

processed_posts = set()


@tasks.loop(seconds=60)
async def check_new_posts():
    global processed_posts
    new_posts = await get_latest_post(subreddit_name, keywords)
    for post in new_posts:
        if post.id not in processed_posts:
            channel_id = 1191526968030679201  # Replace with your Discord channel ID
            channel = bot.get_channel(channel_id)
            if channel:

                embed = discord.Embed(title=post.title,
                                      url=post.url,
                                      description=post.selftext.replace(
                                          "&#x200B;", ""),
                                      color=0x00ff00)
                embed.set_author(
                    name=post.author.name,
                    url=f'https://www.reddit.com/user/{post.author.name}')
                await channel.send(embed=embed)
                processed_posts.add(post.id)


@bot.command()
async def start_crawler(ctx):
    check_new_posts.start()
    await ctx.send('Crawler started!')


@bot.command()
async def stop_crawler(ctx):
    check_new_posts.stop()
    await ctx.send('Crawler stopped!')


async def get_latest_post(subreddit_name, keywords):
    async with asyncpraw.Reddit(client_id=client_id,
                                client_secret=client_secret,
                                user_agent=user_agent) as reddit:
        subreddit = await reddit.subreddit(subreddit_name)
        filtered_posts = []
        async for post in subreddit.new(limit=20):
            title_lower = post.title.lower()
            if any(keyword.lower() in title_lower for keyword in keywords):
                filtered_posts.append(post)
    return filtered_posts


def check_appointment_availability(base_url):
    # Set up options for the Chrome driver
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Specify the path for the Chrome WebDriver
    service = Service()  # Update with the actual Chrome WebDriver path
    driver = webdriver.Chrome(service=service, options=chrome_options)

    all_available_slots = []  # Store all available slots for the 4 dates

    try:
        # Loop for today and the next 3 increments of 7 days (total 4 times)
        for increment in range(8):
            # Calculate the date for the current increment
            current_date = (datetime.today() +
                            timedelta(days=increment * 7)).strftime('%Y-%m-%d')
            url_with_date = f"{base_url}{current_date}"

            # Navigate to the booking page
            driver.get(url_with_date)

            # Wait for the page to load and give extra time for dynamic content
            wait = WebDriverWait(driver, 10)
            wait.until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, 'schedule-main')))
            time.sleep(5)  # Add extra time for dynamic content to load

            # Find all available appointment slots
            available_slots = driver.find_elements(By.CSS_SELECTOR, 'a.apt')

            available_slots_info = []
            for slot in available_slots:
                href = slot.get_attribute('href')
                if href:
                    # Parse the URL and extract the date (dt) and time (st)
                    parsed_url = urlparse(href)
                    query_params = parse_qs(parsed_url.query)
                    date = query_params.get('dt',
                                            [''])[0]  # Extract 'dt' parameter
                    timee = query_params.get('st',
                                             [''])[0]  # Extract 'st' parameter

                    # Append date and time information to available_slots_info
                    available_slots_info.append({
                        'day': f"{date} {timee}",
                        'href': href,
                    })

            # Count the number of available slots
            available_count = len(available_slots_info)

            # Append the date and available slots info to all_available_slots
            all_available_slots.append({
                'date': current_date,
                'slots': available_slots_info,
                'available_count': available_count,
            })

        return {'available_slots': all_available_slots}

    except Exception as e:
        return f"An error occurred: {str(e)}"

    finally:
        driver.quit()


@bot.command()
async def check(ctx):
    base_url = "https://vancouver.yamadataro.jp/booking/store/1?sd="  # Update the base URL if needed
    await ctx.send("Checking appointment availability...")

    def run_check():
        return check_appointment_availability(base_url)

    # Running the blocking `check_appointment_availability` in an executor to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    availability_info = await loop.run_in_executor(None, run_check)

    if 'available_slots' in availability_info:
        # Send the results back to the Discord channel
        for info in availability_info['available_slots']:
            await ctx.send(
                f"Date: {info['date']}, Available Slots: {info['available_count']}"
            )
            for slot in info['slots']:
                await ctx.send(f" - {slot['day']} (Link: {slot['href']})")
    else:
        await ctx.send("An error occurred while checking availability.")


@tasks.loop(minutes=5)  # Runs every 60 minutes
async def check_appointments_loop():
    base_url = "https://vancouver.yamadataro.jp/booking/store/1?sd="  # Update the base URL if needed
    channel_id = 1191526968030679201  # Replace with your Discord channel ID
    channel = bot.get_channel(channel_id)

    if channel is None:
        print("Could not find the specified channel.")
        return

    await channel.send("Checking appointment availability...")

    def run_check():
        return check_appointment_availability(base_url)

    # Running the blocking `check_appointment_availability` in an executor to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    availability_info = await loop.run_in_executor(None, run_check)

    if 'available_slots' in availability_info:
        # Send the results back to the Discord channel
        for info in availability_info['available_slots']:
            await channel.send(f"Date: {info['date']}, Available Slots: {info['available_count']}")
            for slot in info['slots']:
                await channel.send(f" - {slot['day']} (Link: {slot['href']})")
    else:
        await channel.send("An error occurred while checking availability.")

# Command to start the scheduled task
@bot.command()
async def start_check(ctx):
    if not check_appointments_loop.is_running():
        check_appointments_loop.start()
        await ctx.send('Appointment check started!')

# Command to stop the scheduled task
@bot.command()
async def stop_check(ctx):
    if check_appointments_loop.is_running():
        check_appointments_loop.stop()
        await ctx.send('Appointment check stopped!')

keep_alive()

bot.run(discord_token)
