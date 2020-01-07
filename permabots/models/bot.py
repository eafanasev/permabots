# -*- coding: utf-8 -*-
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from telegram import Bot as TelegramBotAPI
from kik import KikApi
import logging
from permabots.models.base import PermabotsModel
from permabots.models import TelegramUser, TelegramChatState, KikChatState, MessengerChatState
from django.urls import URLResolver
from django.urls.resolvers import RegexPattern
from django.urls import Resolver404
from telegram import ParseMode, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.bot import InvalidToken
from telegram.utils.request import Request
import ast
from django.conf import settings
from permabots import validators
from kik.messages.responses import TextResponse
from kik.messages.text import TextMessage
from kik.messages.keyboards import SuggestedResponseKeyboard
from kik.configuration import Configuration
from messengerbot import MessengerClient, messages
import sys
from permabots import caching
from messengerbot.attachments import TemplateAttachment
from messengerbot.elements import Element, PostbackButton, WebUrlButton
from messengerbot.templates import GenericTemplate
import textwrap

logger = logging.getLogger(__name__)

def traverse(o, tree_types=list):
    if isinstance(o, tree_types):
        for value in o:
            for subvalue in traverse(value, tree_types):
                yield subvalue
    else:
        yield o


@python_2_unicode_compatible
class Bot(PermabotsModel):
    """
    Model representing a Permabot. Its behavior is shared by all service integrations.
    
    """
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='bots', help_text=_("User who owns the bot"), on_delete=models.CASCADE)
    name = models.CharField(_('Name'), max_length=100, db_index=True, help_text=_("Name for the bot"))
    telegram_bot = models.OneToOneField('TelegramBot', verbose_name=_("Telegram Bot"), related_name='bot', 
                                        on_delete=models.SET_NULL, blank=True, null=True,
                                        help_text=_("Telegram Bot"))
    
    kik_bot = models.OneToOneField('KikBot', verbose_name=_("Kik Bot"), related_name='bot',
                                   on_delete=models.SET_NULL, blank=True, null=True,
                                   help_text=_("Kik Bot"))
    messenger_bot = models.OneToOneField('MessengerBot', verbose_name=_("Messenger Bot"), related_name='bot',
                                         on_delete=models.SET_NULL, blank=True, null=True,
                                         help_text=_("Messenger Bot"))
    
    class Meta:
        verbose_name = _('Bot')
        verbose_name_plural = _('Bots')    
        
    def __str__(self):
        return '%s' % self.name
    
    def update_chat_state(self, bot_service, message, chat_state, target_state, context):
        context_target_state = chat_state.state.name.lower().replace(" ", "_") if chat_state else '_start'
        if not chat_state:
                logger.warning("Chat/sender state for update chat %s not exists" % 
                               (bot_service.get_chat_id(message)))
                bot_service.create_chat_state(message, target_state, {context_target_state: context})
        else:
            if chat_state.state != target_state:                
                state_context = chat_state.ctx
                state_context[context_target_state] = context
                chat_state.ctx = state_context
                chat_state.state = target_state
                chat_state.save()
                logger.debug("Chat state updated:%s for message %s with (%s,%s)" % 
                             (target_state, message, chat_state.state, context))
            else:
                logger.debug("ChateState stays in %s" % target_state)
    
    def handle_message(self, message, bot_service):
        """
        Process incoming message generating a response to the sender.
        
        :param message: Generic message received from provider
        :param bot_service: Service Integration
        :type bot_service: IntegrationBot :class:`IntegrationBot <permabots.models.bot.IntegrationBot>`

        .. note:: Message content will be extracted by IntegrationBot
        """
        urlpatterns = []
        state_context = {}
        chat_state = bot_service.get_chat_state(message)
        for handler in caching.get_or_set_related(self, 'handlers', 'response', 'request', 'target_state'):
            if handler.enabled:
                source_states = caching.get_or_set_related(handler, 'source_states')
                if chat_state:
                    state_context = chat_state.ctx
                if not source_states or (chat_state and chat_state.state in source_states):
                        urlpatterns.append(handler.urlpattern())

        resolver = URLResolver(RegexPattern(r'^'), urlpatterns)
        try:
            resolver_match = resolver.resolve(bot_service.message_text(message))
        except Resolver404:
            logger.warning("Handler not found for %s" % message)
        else:
            callback, callback_args, callback_kwargs = resolver_match
            logger.debug("Calling callback:%s for message %s with %s" % 
                         (callback, message, callback_kwargs))
            text, keyboard, target_state, context = callback(self, message=message, service=bot_service.identity, 
                                                             state_context=state_context, **callback_kwargs)
            if target_state:
                self.update_chat_state(bot_service, message, chat_state, target_state, context)
            keyboard = bot_service.build_keyboard(keyboard)
            bot_service.send_message(bot_service.get_chat_id(message), text, keyboard, message)
            
    def handle_hook(self, hook, data):
        """
        Process notification hook.
        
        :param hook: Notification hook to process
        :type hook: Hook :class:`Hook <permabots.models.hook.Hook>`
        :param data: JSON data from webhook POST
        
        """
        logger.debug("Calling hook %s process: with %s" % (hook.key, data))
        text, keyboard = hook.process(self, data)
        if hook.bot.telegram_bot and hook.bot.telegram_bot.enabled:
            telegram_keyboard = hook.bot.telegram_bot.build_keyboard(keyboard)
            for recipient in hook.telegram_recipients.all():
                hook.bot.telegram_bot.send_message(recipient.chat_id, text, telegram_keyboard)
        if hook.bot.kik_bot and hook.bot.kik_bot.enabled:
            kik_keyboard = hook.bot.kik_bot.build_keyboard(keyboard)
            for recipient in hook.kik_recipients.all():
                hook.bot.kik_bot.send_message(recipient.chat_id, text, kik_keyboard, user=recipient.username)
        if hook.bot.messenger_bot and hook.bot.messenger_bot.enabled:
            messenger_keyboard = hook.bot.messenger_bot.build_keyboard(keyboard)
            for recipient in hook.messenger_recipients.all():
                hook.bot.messenger_bot.send_message(recipient.chat_id, text, messenger_keyboard)
            
class IntegrationBot(PermabotsModel): 
    """
    Abstract class to integrate new instant messaging service.
    """
    enabled = models.BooleanField(_('Enable'), default=True, help_text=_("Enable/disable telegram bot"))
       
    class Meta:
        verbose_name = _('Integration Bot')
        verbose_name_plural = _('Integration Bots')
        abstract = True
        
    def init_bot(self):
        """
        Implement this method to perform some specific intialization to the bot
        """
        raise NotImplementedError
    
    def set_webhook(self, url):
        """
        Implement this method set webhook if the services requires
        
        :param url: URL generated to use for this bot
        """
        raise NotImplementedError
    
    @property
    def hook_url(self):
        """
        Name of the view to resolve url. i.e. permabots:telegrambot
        :returns: Named view
        """
        raise NotImplementedError
        
    @property
    def hook_id(self):
        """
        Identifier to generate webhook url i.e. primary key UUID
        
        :returns: Identifier
        :rtype: string
        """
        raise NotImplementedError
    
    @property
    def identity(self):
        """
        Some service identifier to attach in processing context i.e. telegram.
        
        :returns: Service Indentifier
        :rtype: string
        """
        raise NotImplemented
    
    @property
    def null_url(self):
        """
        Return a none URL to remove webhook. i.e.: None
        
        :returns: None url
        
        .. note:: Some providers API accepts None but others need a real url. Use https://example.com in this case
        
        """
        raise NotImplementedError
    
    def message_text(self, message):
        """
        Extract text message from generic message
        :param message: Message from provider
        :returns: text from message
        :rtype: string
        """
        raise NotImplementedError
    
    def get_chat_id(self, message):
        """
        Extract chat identifier from service message.
        
        :param message: Message from provider
        :returns: chat identifier
        """
        raise NotImplementedError
    
    def get_chat_state(self, message):
        """
        Each integration has its own chat state model. Implement this method to obtain it from message
        
        :param message: Message from provider
        :returns: generic chat state
        """
        raise NotImplementedError
        
    def build_keyboard(self, keyboard):
        """
        From an arrays of strings generated specific keyboard for integration
        
        :param keyboard: list(strings)
        :returns: specific keyboard  
        """
        raise NotImplementedError
        
    def send_message(self, chat_id, text, keyboard, reply_message=None, user=None):
        """
        Send message with the a response generated.
        
        :param chat_id: Identifier for the chat
        :param text: Text response
        :param keyboard: Keyboard response
        :param reply_message: Message to reply
        :param user: When no replying in some providers is not enough with chat_id
        
        .. note:: Each provider has its own limits for texts and keyboards buttons. Implement here how to split a response to several messages.
        """
        raise NotImplementedError
    
    def create_chat_state(self, message, target_state, context):
        """
        Crate specific chat state modelling for the integration. It is called only when first chat interaction is performed by a user.
        
        :param message: Message from the provider
        :param target_state: State to set
        :param context: Processing generated in the processing
        """
        raise NotImplementedError
    
    def batch(self, iterable, n=1):
        l = len(iterable)
        for ndx in range(0, l, n):
            last = ndx+n >= l
            yield iterable[ndx:min(ndx+n, l)], last
               
@python_2_unicode_compatible
class TelegramBot(IntegrationBot):
    """
    Telegram integration. 
    
    Permabots only requires token to set webhook and obtain some bot info.
    
    Follow telegram instructions to create a bot and obtain its token `<https://core.telegram.org/bots#botfather>`_.
    """
    token = models.CharField(_('Token'), max_length=100, db_index=True, unique=True, validators=[validators.validate_token],
                             help_text=_("Token provided by Telegram API https://core.telegram.org/bots"))
    user_api = models.OneToOneField(TelegramUser, verbose_name=_("Telegram Bot User"), related_name='telegram_bot', 
                                    on_delete=models.CASCADE, blank=True, null=True,
                                    help_text=_("Telegram API info. Automatically retrieved from Telegram"))
    
    class Meta:
        verbose_name = _('Telegram Bot')
        verbose_name_plural = _('Telegram Bots')    
    
    def __init__(self, *args, **kwargs):
        super(TelegramBot, self).__init__(*args, **kwargs)
        self._bot = None
        if self.token:
            try:
                self.init_bot()
            except InvalidToken:
                logger.warning("Incorrect token %s" % self.token)
            
    def __str__(self):
        return "%s" % (self.user_api.first_name or self.token if self.user_api else self.token)
    
    def init_bot(self):
        self._bot = TelegramBotAPI(self.token)
    
    @property
    def hook_id(self):
        return str(self.id)
    
    @property
    def hook_url(self):
        return 'permabots:telegrambot'
    
    @property
    def null_url(self):
        return None
    
    @property
    def identity(self):
        return 'telegram'
    
    def set_webhook(self, url):
        self._bot.set_webhook(webhook_url=url)
        
    def _get_chat_and_user(self, update):
        if update.message:
            chat = update.message.chat
            user = update.message.from_user
        elif update.callback_query:
            chat = update.callback_query.message.chat
            user = update.callback_query.from_user
        return chat, user

    def message_text(self, message):
        if message.message:
            return message.message.text
        elif message.callback_query:
            return message.callback_query.data
    
    def get_chat_state(self, message):
        chat, user = self._get_chat_and_user(message)
        try:
            return TelegramChatState.objects.select_related('state', 'chat', 'user').get(chat=chat, user=user, state__bot=self.bot)
        except TelegramChatState.DoesNotExist:
            return None
        
    def _create_keyboard_button(self, element):
        if isinstance(element, tuple):
            if 'http' in element[1]:
                return InlineKeyboardButton(text=element[0], url=element[1])
            else:
                return InlineKeyboardButton(text=element[0], callback_data=element[1])
        else:
            return InlineKeyboardButton(text=element, callback_data=element)
        
    def build_keyboard(self, keyboard):       
        built_keyboard = []
        if keyboard:
            built_keyboard = InlineKeyboardMarkup([[self._create_keyboard_button(element)] for element in traverse(ast.literal_eval(keyboard))])
        else:
            built_keyboard = ReplyKeyboardHide()
        return built_keyboard
        
    def create_chat_state(self, message, target_state, context):
        chat, user = self._get_chat_and_user(message)
        TelegramChatState.objects.create(chat=chat,
                                         user=user,
                                         state=target_state,
                                         ctx=context)
              
    def get_chat_id(self, message):
        chat, user = self._get_chat_and_user(message)
        return chat.id
    
    def send_message(self, chat_id, text, keyboard, reply_message=None, user=None):
        parse_mode = ParseMode.HTML
        disable_web_page_preview = True
        reply_to_message_id = None
        if reply_message:
            if reply_message.message:
                reply_to_message_id = reply_message.message.message_id
            elif reply_message.callback_query:
                reply_to_message_id = reply_message.callback_query.message.message_id
        texts = text.strip().split('\\n')
        msgs = []
        for txt in texts:
            for chunk in textwrap.wrap(txt, 4096):
                msgs.append((chunk, None))
        if keyboard:
            msgs[-1] = (msgs[-1][0], keyboard)
        for msg in msgs:
            try:
                logger.debug("Message to send:(chat:%s,text:%s,parse_mode:%s,disable_preview:%s,keyboard:%s, reply_to_message_id:%s" %
                             (chat_id, msg[0], parse_mode, disable_web_page_preview, msg[1], reply_to_message_id))
                self._bot.send_message(chat_id=chat_id, text=msg[0], parse_mode=parse_mode, 
                                       disable_web_page_preview=disable_web_page_preview, reply_markup=msg[1], 
                                       reply_to_message_id=reply_to_message_id)        
                logger.debug("Message sent OK:(chat:%s,text:%s,parse_mode:%s,disable_preview:%s,reply_keyboard:%s, reply_to_message_id:%s" %
                             (chat_id, msg[0], parse_mode, disable_web_page_preview, msg[1], reply_to_message_id))
            except:
                exctype, value = sys.exc_info()[:2] 
                
                logger.error("""Error trying to send message:(chat:%s,text:%s,parse_mode:%s,disable_preview:%s,
                             reply_keyboard:%s, reply_to_message_id:%s): %s:%s""" % 
                             (chat_id, msg[0], parse_mode, disable_web_page_preview, msg[1], reply_to_message_id, exctype, value))
                
            
@python_2_unicode_compatible
class KikBot(IntegrationBot):
    """
    Kik integration.
    
    Permabots sets webhook. Only requires api_key and username from Kik provider.
    
    Follow Kik instructons to create a bot and obtain username and api_key `<https://dev.kik.com/>`_.
    """
    api_key = models.CharField(_('Kik Bot API key'), max_length=200, db_index=True)
    username = models.CharField(_("Kik Bot User name"), max_length=200)
   
    class Meta:
        verbose_name = _('Kik Bot')
        verbose_name_plural = _('Kik Bots')    
    
    def __init__(self, *args, **kwargs):
        super(KikBot, self).__init__(*args, **kwargs)
        self._bot = None
        if self.api_key and self.username:
            self.init_bot()
           
    def __str__(self):
        return "%s" % self.username
    
    def __repr__(self):
        return "(%s, %s)" % (self.username, self.api_key)
    
    def init_bot(self):
        self._bot = KikApi(self.username, self.api_key)
    
    def set_webhook(self, url):
        self._bot.set_configuration(Configuration(webhook=url))
    
    @property
    def hook_url(self):
        return 'permabots:kikbot'
    
    @property
    def hook_id(self):
        return str(self.id)
    
    @property
    def null_url(self):
        return "https://example.com"
    
    @property
    def identity(self):
        return 'kik'
    
    def message_text(self, message):
        return message.body
    
    def get_chat_state(self, message):
        try:
            return KikChatState.objects.select_related('state', 'chat', 'user').get(chat=message.chat, user=message.from_user, state__bot=self.bot)
        except KikChatState.DoesNotExist:
            return None
        
    def _create_keyboard_button(self, element):
        # Extend Kik for Link buttons
        if isinstance(element, tuple):
            return TextResponse(body=element[0])
        else:
            return TextResponse(body=element)
        
    def build_keyboard(self, keyboard):                
        built_keyboard = []
        if keyboard:
            built_keyboard = [self._create_keyboard_button(element) for element in traverse(ast.literal_eval(keyboard))][:20]           
        return built_keyboard
    
    def create_chat_state(self, message, target_state, context):
        KikChatState.objects.create(chat=message.chat,
                                    user=message.from_user,
                                    state=target_state,
                                    ctx=context)

    def get_chat_id(self, message):
        return message.chat.id
    
    def send_message(self, chat_id, text, keyboard, reply_message=None, user=None):
        if reply_message:
            to = reply_message.from_user.username
        if user:
            to = user
        texts = text.strip().split('\\n')
        msgs = []
        for txt in texts:
            for chunk in textwrap.wrap(txt, 100):
                msg = TextMessage(to=to, chat_id=chat_id, body=chunk)
                msgs.append(msg)
        if keyboard:
            msgs[-1].keyboards.append(SuggestedResponseKeyboard(to=to, responses=keyboard))
        try:
            logger.debug("Messages to send:(%s)" % str([m.to_json() for m in msgs]))
            self._bot.send_messages(msgs)    
            logger.debug("Message sent OK:(%s)" % str([m.to_json() for m in msgs]))
        except:
            exctype, value = sys.exc_info()[:2]
            logger.error("Error trying to send message:(%s): %s:%s" % (str([m.to_json() for m in msgs]), exctype, value))
            
@python_2_unicode_compatible
class MessengerBot(IntegrationBot):
    """
    Facebook Messenger integration. 
    
    Permabots only uses Page Access Token but webhook is not set. It mus be set manually in Facebook dev platform using 
    UUID generated as id of the messenger bot after creation in Permabots.
    
    This bot is used to Verify Token and  generate url https://domain/processing/messengerbot/permabots_messenger_bot_id/
    
    Read Messenger documentation `<https://developers.facebook.com/docs/messenger-platform/quickstart>` _.
    """
    token = models.CharField(_('Messenger Token'), max_length=512, db_index=True)
    
    class Meta:
        verbose_name = _('Messenger Bot')
        verbose_name_plural = _('Messenger Bots')    
    
    def __init__(self, *args, **kwargs):
        super(MessengerBot, self).__init__(*args, **kwargs)
        self._bot = None
        self.webhook = False
        if self.token:
            self.init_bot()
           
    def __str__(self):
        return "%s" % self.token
    
    def __repr__(self):
        return "(%s, %s)" % (self.id, self.token)
    
    def init_bot(self):
        self._bot = MessengerClient(self.token)
    
    def set_webhook(self, url):
        # Url is set in facebook dashboard. Just subscribe
        self._bot.subscribe_app() 

    @property
    def hook_url(self):
        return 'permabots:messengerbot'
    
    @property
    def hook_id(self):
        return str(self.id)
    
    @property
    def null_url(self):
        # not used
        return "https://example.com"
    
    @property
    def identity(self):
        return 'messenger'
    
    def message_text(self, message):
        return message.data
    
    def get_chat_state(self, message):
        try:
            return MessengerChatState.objects.select_related('state').get(chat=message.sender, state__bot=self.bot)
        except MessengerChatState.DoesNotExist:
            return None
        
    def _create_keyboard_button(self, element):
        if isinstance(element, tuple):
            if 'http' in element[1]:
                return WebUrlButton(title=element[0][0:20], url=element[1])
            else:
                return PostbackButton(title=element[0][0:20], payload=element[1])
        else:
            return PostbackButton(title=element[0:20], payload=element)
        
    def build_keyboard(self, keyboard):     
        built_keyboard = None
        if keyboard:
            # same payload as title
            built_keyboard = [self._create_keyboard_button(element) for element in traverse(ast.literal_eval(keyboard))]
        return built_keyboard
    
    def create_chat_state(self, message, target_state, context):
        MessengerChatState.objects.create(chat=message.sender,
                                          state=target_state,
                                          ctx=context)

    def get_chat_id(self, message):
        return message.sender
        
    def send_message(self, chat_id, text, keyboard, reply_message=None, user=None):
        texts = text.strip().split('\\n')
        msgs = []
        for txt in texts:             
            for chunk in textwrap.wrap(txt, 320):
                msgs.append(messages.Message(text=chunk))

        if keyboard:
            if len(msgs[-1].text) <= 45:
                title = msgs.pop().text
            else:
                new_texts = textwrap.wrap(msgs[-1].text, 45)
                msgs[-1].text = " ".join(new_texts[:-1])
                title = new_texts[-1]
            elements = []
            for chunk_buttons, last in self.batch(keyboard[0:30], 3):
                elements.append(Element(title=title, buttons=chunk_buttons))
            generic_template = GenericTemplate(elements)
            attachment = TemplateAttachment(generic_template)
            msgs.append(messages.Message(attachment=attachment))
        
        for msg in msgs:
            try:
                logger.debug("Message to send:(%s)" % msg.to_dict())
                recipient = messages.Recipient(recipient_id=chat_id)
                self._bot.send(messages.MessageRequest(recipient, msg))
                logger.debug("Message sent OK:(%s)" % msg.to_dict())
            except:
                exctype, value = sys.exc_info()[:2] 
                logger.error("Error trying to send message:(%s): %s:%s" % (msg.to_dict(), exctype, value))
