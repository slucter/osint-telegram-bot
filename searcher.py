import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import tempfile
import re
from pathlib import Path
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from elasticsearch import AsyncElasticsearch
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from tqdm.asyncio import tqdm

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Elasticsearch configuration
ES_HOST = os.getenv('ES_HOST', '')
ES_USER = os.getenv('ES_USERNAME', '')
ES_PASS = os.getenv('ES_PASSWORD', '')
ES_INDEX = os.getenv('ES_INDEX', '')

# Telegram configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')

# Database configuration
Base = declarative_base()
engine = create_engine('sqlite:///bot_users.db')
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    user_id = Column(Integer, primary_key=True)
    username = Column(String)
    count_search = Column(Integer, default=0)
    last_search_date = Column(DateTime)
    is_blocked = Column(Boolean, default=False)
    type = Column(String, default='free')  # free, premium, vip, superuser
    start_date_premium = Column(DateTime, nullable=True)
    end_date_premium = Column(DateTime, nullable=True)

# Create tables
Base.metadata.create_all(engine)

# Initialize Elasticsearch client with better timeout settings
es = AsyncElasticsearch(
    [ES_HOST],
    basic_auth=(ES_USER, ES_PASS),
    verify_certs=False,
    max_retries=3,  # Number of retries
    retry_on_timeout=True,  # Retry on timeout
    request_timeout=30  # Request timeout in seconds
)

async def get_or_create_user(user_id: int, username: str) -> tuple[User, Session]:
    session = Session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            # Check if this is the first user
            is_first_user = session.query(User).count() == 0
            user_type = 'superuser' if is_first_user else 'free'
            
            user = User(
                user_id=user_id,
                username=username,
                type=user_type
            )
            session.add(user)
            session.commit()
        return user, session
    except Exception as e:
        session.close()
        raise e

def format_timedelta(td):
    """Format timedelta to a more readable string"""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    elif minutes > 0:
        return f"{minutes:02d}:{seconds:02d}"
    else:
        return f"{seconds:02d} seconds"

async def search_elasticsearch(field: str, keyword: str, user_type: str, progress_callback) -> List[Dict[str, Any]]:
    max_retries = 3
    retry_delay = 5
    start_time = datetime.now()
    
    try:
        for attempt in range(max_retries):
            try:
                # Create search query
                query = {
                    "query": {
                        "bool": {
                            "should": [
                                {
                                    "wildcard": {
                                        "url": f"*{keyword}*"
                                    }
                                },
                                {
                                    "wildcard": {
                                        "username": f"*{keyword}*"
                                    }
                                },
                                {
                                    "wildcard": {
                                        "password": f"*{keyword}*"
                                    }
                                }
                            ],
                            "minimum_should_match": 1
                        }
                    }
                }
                
                logger.info(f"Starting search for keyword: {keyword}, user_type: {user_type}, attempt {attempt + 1}/{max_retries}")
                
                # First, get the total count
                await progress_callback(
                    "🔍 Counting available results...\n"
                    "⏳ Please wait..."
                )
                
                try:
                    count_response = await es.count(
                        index=ES_INDEX,
                        body=query,
                        request_timeout=30
                    )
                    total_hits = count_response['count']
                    logger.info(f"Total hits found: {total_hits}")
                    
                    if total_hits == 0:
                        logger.info("No results found")
                        return []
                        
                    await progress_callback(
                        f"📊 Found {total_hits:,} results\n"
                        f"🔄 Starting data processing...\n"
                        f"⏳ Progress: 0%"
                    )
                except Exception as e:
                    logger.error(f"Error during count operation: {str(e)}", exc_info=True)
                    if attempt < max_retries - 1:
                        await progress_callback(f"⚠️ Connection error, retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        continue
                    raise Exception(f"Failed to count results after {max_retries} attempts: {str(e)}")
                
                # Use scroll API for large result sets
                results = []
                scroll_size = 10000  # Maximum allowed by default
                processed = 0
                scroll_id = None
                last_update_time = datetime.now()
                update_interval = 1  # Update progress every second
                
                try:
                    # Initial search with scroll
                    search_body = {
                        **query,
                        "size": scroll_size,
                        "sort": ["_doc"]  # Optimize for scrolling
                    }
                    
                    logger.info(f"Initial search with body: {search_body}")
                    
                    response = await es.search(
                        index=ES_INDEX,
                        body=search_body,
                        scroll='10m',  # Keep the scroll context alive for 10 minutes
                        request_timeout=30
                    )
                    
                    # Get the scroll ID
                    scroll_id = response['_scroll_id']
                    logger.info(f"Initial scroll_id: {scroll_id}")
                    
                    # Process first batch
                    hits = response['hits']['hits']
                    while hits:
                        # Add results from current batch
                        batch_results = [hit['_source'] for hit in hits]
                        results.extend(batch_results)
                        processed += len(hits)
                        
                        # Update progress every second
                        current_time = datetime.now()
                        if (current_time - last_update_time).total_seconds() >= update_interval:
                            progress = min(100, int((processed / total_hits) * 100))
                            elapsed_time = current_time - start_time
                            speed = processed / elapsed_time.total_seconds() if elapsed_time.total_seconds() > 0 else 0
                            eta = (total_hits - processed) / speed if speed > 0 else 0
                            
                            # Create progress bar
                            progress_bar = "█" * (progress // 5) + "░" * (20 - (progress // 5))
                            
                            await progress_callback(
                                f"🔄 Processing Results\n\n"
                                f"Progress: {progress}%\n"
                                f"[{progress_bar}]\n\n"
                                f"📊 Statistics:\n"
                                f"• Processed: {processed:,}/{total_hits:,} results\n"
                                f"• Speed: {speed:.1f} results/second\n"
                                f"• Elapsed: {format_timedelta(elapsed_time)}\n"
                                f"• ETA: {format_timedelta(timedelta(seconds=int(eta)))}"
                            )
                            last_update_time = current_time
                        
                        # Log detailed progress
                        logger.info(f"Batch processed: {len(hits)} hits, Total processed: {processed:,}/{total_hits:,}")
                        
                        # Get next batch
                        try:
                            scroll_response = await es.scroll(
                                scroll_id=scroll_id,
                                scroll='10m',
                                request_timeout=30
                            )
                            hits = scroll_response['hits']['hits']
                            logger.info(f"Next batch size: {len(hits)} hits")
                        except Exception as e:
                            logger.error(f"Error during scroll operation: {str(e)}", exc_info=True)
                            if attempt < max_retries - 1:
                                await progress_callback(f"⚠️ Connection error, retrying in {retry_delay} seconds...")
                                await asyncio.sleep(retry_delay)
                                break  # Break the while loop to retry the entire search
                            raise Exception(f"Failed to fetch next batch after {max_retries} attempts: {str(e)}")
                    
                    # Clear scroll context
                    if scroll_id:
                        try:
                            await es.clear_scroll(scroll_id=scroll_id)
                            logger.info("Scroll context cleared successfully")
                        except Exception as e:
                            logger.warning(f"Failed to clear scroll: {str(e)}")
                    
                    logger.info(f"Total results collected: {len(results):,}")
                    
                    if len(results) != total_hits:
                        logger.warning(f"Discrepancy in results: Expected {total_hits:,} but got {len(results):,}")
                        if attempt < max_retries - 1:
                            await progress_callback("⚠️ Data verification failed, retrying...")
                            await asyncio.sleep(retry_delay)
                            continue
                    
                    if user_type == 'free':
                        # Limit to 40% of results for free users
                        original_count = len(results)
                        results = results[:int(len(results) * 0.4)]
                        logger.info(f"Applied free user limit: {len(results)} results (40% of {original_count})")
                        await progress_callback(
                            f"✅ Processing Complete!\n\n"
                            f"ℹ️ Free user limit applied:\n"
                            f"• Original results: {original_count:,}\n"
                            f"• Limited results: {len(results):,}\n\n"
                            f"💎 Upgrade to Premium for:\n"
                            f"• Get 100% of results\n"
                            f"• No daily limits\n"
                            f"• Unlimited searches\n"
                            f"• Contact: @xlcert"
                        )
                    else:
                        await progress_callback(
                            f"✅ Processing Complete!\n\n"
                            f"📊 Results Summary:\n"
                            f"• Total results: {len(results):,}\n"
                            f"• Processing time: {format_timedelta(datetime.now() - start_time)}"
                        )
                    
                    return results
                    
                except Exception as e:
                    logger.error(f"Error during search operation: {str(e)}", exc_info=True)
                    # Try to clear scroll context if it exists
                    if scroll_id:
                        try:
                            await es.clear_scroll(scroll_id=scroll_id)
                        except:
                            pass
                    if attempt < max_retries - 1:
                        await progress_callback(f"⚠️ Operation failed, retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        continue
                    raise Exception(f"Search operation failed after {max_retries} attempts: {str(e)}")
                
            except Exception as e:
                logger.error(f"Elasticsearch error: {str(e)}", exc_info=True)
                if attempt < max_retries - 1:
                    await progress_callback(f"⚠️ System error, retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    continue
                raise Exception(f"Elasticsearch error after {max_retries} attempts: {str(e)}")
        
        raise Exception(f"Failed to complete search after {max_retries} attempts")
    finally:
        pass

async def format_results(results: List[Dict[str, Any]], keyword: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    header = f"_TFROB.ID_\nDate Search: {now}\nKeyword: {keyword}\nTotal result: {len(results)}\n\n"
    
    formatted_results = []
    for result in results:
        formatted_results.append(f"{result.get('url', '')}:{result.get('username', '')}:{result.get('password', '')}")
    
    return header + "\n".join(formatted_results)

async def create_result_file(content: str, keyword: str) -> str:
    # Create a temporary file
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    # Escape special characters in keyword
    safe_keyword = re.sub(r'[^a-zA-Z0-9]', '_', keyword)
    # Ensure keyword is not too long
    safe_keyword = safe_keyword[:50]  # Limit keyword length to 50 characters
    filename = f"TFROB_{safe_keyword}_{timestamp}.txt"
    
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filepath

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, session = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    try:
        welcome_message = (
            f"Welcome to TFROB Search Bot!\n"
            f"Your account type: {user.type}\n\n"
            "Available commands:\n"
            "/search <field>:<keyword> - Search by specific field\n"
            "/search <keyword> - Search by URL (default)\n"
        )
        
        if user.type == 'superuser':
            welcome_message += (
                "\nAdmin commands:\n"
                "/setpremium <user_id> <date> - Set premium status\n"
                "/blockuser <user_id> - Block a user\n"
                "/users <type> - List users by type\n"
            )
        
        await update.message.reply_text(welcome_message)
    finally:
        session.close()

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, session = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    try:
        if user.is_blocked:
            await update.message.reply_text("🚫 Your account has been blocked.")
            return
        
        if user.type == 'free':
            today = datetime.now().date()
            if user.last_search_date and user.last_search_date.date() == today:
                if user.count_search >= 15:
                    await update.message.reply_text("⚠️ Free users are limited to 15 searches per day.")
                    return
            else:
                user.count_search = 0
        
        # Parse search query
        query = ' '.join(context.args)
        if ':' in query:
            field, keyword = query.split(':', 1)
            if field not in ['url', 'username', 'password']:
                await update.message.reply_text("❌ Invalid field. Use: url, username, or password")
                return
        else:
            field = 'url'
            keyword = query
        
        logger.info(f"User {user.user_id} ({user.type}) searching for {keyword}")
        
        # Send initial progress message
        progress_message = await update.message.reply_text(
            f"🚀 Starting flexible search for '{keyword}'...\n"
            f"👤 User type: {user.type.upper()}\n"
            f"⏱️ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📊 Please wait while we process your request..."
        )
        
        async def update_progress(message: str):
            try:
                await progress_message.edit_text(
                    f"🚀 Searching '{keyword}'...\n"
                    f"👤 User type: {user.type.upper()}\n"
                    f"⏱️ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"{message}"
                )
            except Exception as e:
                logger.error(f"Error updating progress message: {str(e)}", exc_info=True)
        
        try:
            # Perform search
            results = await search_elasticsearch(field, keyword, user.type, update_progress)
            
            if not results:
                await update.message.reply_text("❌ No results found for your search query.")
                return
            
            # Update user stats
            user.count_search += 1
            user.last_search_date = datetime.now()
            session.commit()
            
            # Format and send results
            formatted_results = await format_results(results, keyword)
            
            # Create and send result file
            filepath = await create_result_file(formatted_results, keyword)
            
            # Split results if needed
            max_rows = 100000 if user.type == 'free' else 150000
            total_rows = len(results)
            
            await update_progress(
                f"✅ Search completed!\n"
                f"📊 Total results: {total_rows:,}\n"
                f"⏱️ Time: {datetime.now().strftime('%H:%M:%S')}\n"
                f"📦 Preparing to send results..."
            )
            
            if total_rows > max_rows:
                parts = (total_rows + max_rows - 1) // max_rows
                await update.message.reply_text(
                    f"📦 Results will be split into {parts} parts:\n"
                    f"• Total results: {total_rows:,}\n"
                    f"• Max rows per part: {max_rows:,}\n"
                    f"• Number of parts: {parts}"
                )
                
                for i in range(parts):
                    start_idx = i * max_rows
                    end_idx = min((i + 1) * max_rows, total_rows)
                    part_results = results[start_idx:end_idx]
                    
                    # Format part results with header
                    part_header = f"_TFROB.ID_\nDate Search: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nKeyword: {keyword}\nPart: {i+1}/{parts}\nTotal result: {len(part_results)}\n\n"
                    part_content = part_header + "\n".join([f"{r.get('url', '')}:{r.get('username', '')}:{r.get('password', '')}" for r in part_results])
                    
                    # Create and send part file
                    part_filepath = await create_result_file(part_content, f"{keyword}_part{i+1}")
                    
                    try:
                        with open(part_filepath, 'rb') as f:
                            await update.message.reply_document(
                                document=f,
                                filename=os.path.basename(part_filepath),
                                caption=f"Part {i+1}/{parts} - {len(part_results):,} results"
                            )
                    except Exception as e:
                        logger.error(f"Error sending part {i+1}: {str(e)}", exc_info=True)
                        await update.message.reply_text(f"❌ Error sending part {i+1}: {str(e)}")
                    finally:
                        if os.path.exists(part_filepath):
                            os.remove(part_filepath)
            else:
                try:
                    with open(filepath, 'rb') as f:
                        await update.message.reply_document(
                            document=f,
                            filename=os.path.basename(filepath)
                        )
                except Exception as e:
                    logger.error(f"Error sending file: {str(e)}", exc_info=True)
                    await update.message.reply_text(f"❌ Error sending file: {str(e)}")
                finally:
                    if os.path.exists(filepath):
                        os.remove(filepath)
            
            # Send completion message
            completion_message = (
                f"✨ Search Results Summary:\n"
                f"🔍 Keyword: {keyword}\n"
                f"📊 Total Results: {total_rows:,}\n"
                f"⏱️ Search Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"👤 User Type: {user.type.upper()}\n"
                f"📈 Search Count Today: {user.count_search}{'/' + str(15) if user.type == 'free' else ''}"
            )
            
            await update.message.reply_text(completion_message)
            
            # Send subscription info for free users
            if user.type == 'free':
                subscription_info = (
                    "💎 Upgrade to Premium for:\n"
                    "• Contact: @xlcert\n"
                    "• Get 100% of results\n"
                    "• No daily limits\n"
                    "• Unlimited searches\n\n"
                    "📅 Subscription Plans:\n"
                    "• 3 days: $4\n"
                    "• 1 week: $7\n"
                    "• 1 month: $20\n"
                    "• 3 months: $50\n"
                    "• Lifetime: $100\n\n"
                    "ℹ️ Current Free User Limits:\n"
                    "• 15 searches per day\n"
                    "• 40% of total results\n"
                    "• Maximum 100,000 rows per search"
                )
                await update.message.reply_text(subscription_info)
                
        except Exception as e:
            error_message = f"An error occurred while processing your request: {str(e)}"
            logger.error(error_message, exc_info=True)
            await update.message.reply_text(
                "❌ Server Error\n"
                "We encountered an issue while processing your request.\n"
                f"Error details: {str(e)}\n"
                "Please try again later or contact support if the problem persists."
            )
            
    except Exception as e:
        logger.error(f"Unexpected error in search function: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ Unexpected Error\n"
            "An unexpected error occurred.\n"
            f"Error details: {str(e)}\n"
            "Please try again later or contact support if the problem persists."
        )
    finally:
        session.close()

async def setpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) != 2:
        await update.message.reply_text("Usage: /setpremium <user_id> <date>")
        return
    
    user, session = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    try:
        if not user or user.type != 'superuser':
            await update.message.reply_text("This command is only available for superusers.")
            return
        
        target_user_id = int(context.args[0])
        end_date = datetime.strptime(context.args[1], "%d-%m-%Y")
        
        if end_date < datetime.now():
            await update.message.reply_text("End date cannot be in the past.")
            return
        
        target_user = session.query(User).filter_by(user_id=target_user_id).first()
        if not target_user:
            await update.message.reply_text("User not found.")
            return
        
        target_user.type = 'premium'
        target_user.start_date_premium = datetime.now()
        target_user.end_date_premium = end_date
        session.commit()
        
        await update.message.reply_text(f"Successfully set premium status for user {target_user_id} until {end_date.strftime('%d-%m-%Y')}")
        
    finally:
        session.close()

async def blockuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /blockuser <user_id>")
        return
    
    user, session = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    try:
        if not user or user.type != 'superuser':
            await update.message.reply_text("This command is only available for superusers.")
            return
        
        target_user_id = int(context.args[0])
        target_user = session.query(User).filter_by(user_id=target_user_id).first()
        
        if not target_user:
            await update.message.reply_text("User not found.")
            return
        
        target_user.is_blocked = True
        session.commit()
        
        await update.message.reply_text(f"Successfully blocked user {target_user_id}")
        
    finally:
        session.close()

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /users <type>")
        return
    
    user, session = await get_or_create_user(update.effective_user.id, update.effective_user.username)
    try:
        if not user or user.type != 'superuser':
            await update.message.reply_text("This command is only available for superusers.")
            return
        
        user_type = context.args[0].lower()
        if user_type not in ['all', 'free', 'premium', 'vip']:
            await update.message.reply_text("Invalid type. Use: all, free, premium, or vip")
            return
        
        query = session.query(User)
        if user_type != 'all':
            query = query.filter_by(type=user_type)
        
        users = query.all()
        
        if not users:
            await update.message.reply_text("No users found.")
            return
        
        message = "User List:\n\n"
        for i, u in enumerate(users, 1):
            message += (
                f"{i}. User ID: {u.user_id}\n"
                f"   Username: {u.username}\n"
                f"   Total searches: {u.count_search}\n"
                f"   Last search: {u.last_search_date}\n"
                f"   Type: {u.type}\n"
            )
            if u.type == 'premium':
                message += f"   Premium period: {u.start_date_premium} to {u.end_date_premium}\n"
            message += "\n"
        
        await update.message.reply_text(message)
        
    finally:
        session.close()

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("setpremium", setpremium))
    application.add_handler(CommandHandler("blockuser", blockuser))
    application.add_handler(CommandHandler("users", users))
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
