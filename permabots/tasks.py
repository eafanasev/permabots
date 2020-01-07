from __future__ import absolute_import
from celery import shared_task
from permabots.models import TelegramUpdate, TelegramBot, Hook, KikMessage, KikBot, MessengerMessage, MessengerBot
import logging
import traceback
import sys
from permabots import caching

logger = logging.getLogger(__name__)

@shared_task
def handle_update(update_id, bot_id):
    try:
        update = caching.get_or_set(TelegramUpdate, update_id)
        telegram_bot = caching.get_or_set(TelegramBot, bot_id)
    except TelegramUpdate.DoesNotExist:
        logger.error("Update %s does not exists" % update_id)
    except TelegramBot.DoesNotExist:
        logger.error("Bot  %s does not exists or disabled" % bot_id)
    except:
        logger.error("Error handling update %s from bot %s" % (update_id, bot_id))
    else:
        try:
            telegram_bot.init_bot()
            telegram_bot.bot.handle_message(update, telegram_bot)
        except:           
            exc_info = sys.exc_info()
            traceback.print_exception(*exc_info)
            logger.error("Error processing %s for bot %s" % (update, telegram_bot))
        else:
            # Each update is only used once
            caching.delete(TelegramUpdate, update)

@shared_task          
def handle_message(message_id, bot_id):
    try:
        message = caching.get_or_set(KikMessage, message_id)
        kik_bot = caching.get_or_set(KikBot, bot_id)
    except KikMessage.DoesNotExist:
        logger.error("Message %s does not exists" % message_id)
    except KikBot.DoesNotExist:
        logger.error("Bot  %s does not exists or disabled" % bot_id)
    except:
        logger.error("Error handling update %s from bot %s" % (message_id, bot_id))
    else:
        try:
            kik_bot.bot.handle_message(message, kik_bot)
        except:           
            exc_info = sys.exc_info()
            traceback.print_exception(*exc_info)
            logger.error("Error processing %s for bot %s" % (message, kik_bot))
        else:
            # Each update is only used once
            caching.delete(KikMessage, message)
            
@shared_task          
def handle_messenger_message(message_id, bot_id):
    try:
        message = caching.get_or_set(MessengerMessage, message_id)
        messenger_bot = caching.get_or_set(MessengerBot, bot_id)
    except MessengerMessage.DoesNotExist:
        logger.error("Message %s does not exists" % message_id)
    except MessengerBot.DoesNotExist:
        logger.error("Bot  %s does not exists or disabled" % bot_id)
    except:
        logger.error("Error handling update %s from bot %s" % (message_id, bot_id))
    else:
        try:
            messenger_bot.bot.handle_message(message, messenger_bot)
        except:           
            exc_info = sys.exc_info()
            traceback.print_exception(*exc_info)
            logger.error("Error processing %s for bot %s" % (message, messenger_bot))
        else:
            # Each update is only used once
            caching.delete(MessengerMessage, message)        

            
@shared_task
def handle_hook(hook_id, data):
    try:
        hook = Hook.objects.get(id=hook_id)
    except Hook.DoesNotExist:
        logger.error("Hook %s does not exists" % hook_id)
    else:
        try:
            hook.bot.handle_hook(hook, data)
        except:           
            exc_info = sys.exc_info()
            traceback.print_exception(*exc_info)
            logger.error("Error processing %s for bot %s" % (hook, hook.bot))
