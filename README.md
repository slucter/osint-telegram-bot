# OSINTBOTTELE Search Bot

> ⚠️ **DISCLAIMER**: This project is created for educational purposes only. The bot is designed to demonstrate concepts of:
> - Elasticsearch integration
> - Telegram bot development
> - User management systems
> - Search functionality implementation
> - Data parsing and processing
> - Security best practices
> 
> Please use this knowledge responsibly and ethically.

## Overview

OSINTBOTTELE Search Bot is a Telegram bot that demonstrates the implementation of a search system using Elasticsearch as the backend database. The bot provides functionality to search through indexed credentials with different user access levels and features.

## Features

### Search Capabilities
- Flexible search across multiple fields (URL, username, password)
- Real-time search progress updates
- Result pagination for large datasets
- Support for wildcard searches

### User Management
- Multiple user types (Free, Premium, VIP, Superuser)
- Daily search limits for free users
- Premium subscription system
- User blocking functionality

### Data Processing
- Smart parsing of credential formats
- Automatic file generation for search results
- Progress tracking and statistics
- Error handling and retry mechanisms

## Technical Stack

- **Backend**: Python
- **Database**: Elasticsearch
- **Bot Framework**: python-telegram-bot
- **ORM**: SQLAlchemy
- **Environment Management**: python-dotenv

## Project Structure

```
OSINTBOTTELE/
├── updateULPV2.py    # Credential parser and indexer
├── searcher.py       # Main bot implementation
├── parserULP.py      # Additional parsing utilities
├── requirements.txt  # Project dependencies
└── .env             # Environment configuration
```

## Setup Instructions

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables in `.env`:
```
ES_HOST=your_elasticsearch_host
ES_USERNAME=your_username
ES_PASSWORD=your_password
ES_INDEX=your_index
TELEGRAM_TOKEN=your_telegram_bot_token
```

3. Run the bot:
```bash
python searcher.py
```

## Bot Commands

- `/start` - Initialize bot and show welcome message
- `/search <field>:<keyword>` - Search by specific field
- `/search <keyword>` - Search by URL (default)

### Admin Commands
- `/setpremium <user_id> <date>` - Set premium status
- `/blockuser <user_id>` - Block a user
- `/users <type>` - List users by type

## User Types and Limits

### Free Users
- 15 searches per day
- 40% of total results
- Maximum 100,000 rows per search

### Premium Users
- Unlimited searches
- 100% of results
- No daily limits
- Maximum 150,000 rows per search

## Security Features

- Environment variable management
- User authentication and authorization
- Rate limiting
- Error handling and logging
- Secure credential storage

## Educational Value

This project demonstrates several important concepts in software development:

1. **API Integration**
   - Elasticsearch integration
   - Telegram Bot API implementation

2. **Database Management**
   - Indexing and searching
   - Data structure optimization
   - Query optimization

3. **User Management**
   - Role-based access control
   - Subscription system
   - User tracking and statistics

4. **Error Handling**
   - Retry mechanisms
   - Graceful failure handling
   - Comprehensive logging

5. **Security Practices**
   - Environment variable usage
   - Secure credential management
   - Input validation

## Contributing

Feel free to contribute to this educational project by:
1. Forking the repository
2. Creating a feature branch
3. Submitting a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contact

For educational inquiries or questions about the implementation:
- Telegram: @babiloniaz

---

Remember: This project is for educational purposes only. Use the knowledge gained responsibly and ethically. 