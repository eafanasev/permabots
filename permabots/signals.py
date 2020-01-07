from django.urls import reverse
from django.conf import settings
import logging
from permabots.validators import validate_token
from django.apps import apps
from permabots import caching

logger = logging.getLogger(__name__)

def set_bot_webhook(sender, instance, **kwargs):
    def get_site_domain():
        from django.contrib.sites.models import Site
        current_site = Site.objects.get_current()
        return current_site.domain
    
    #  set bot api if not yet
    if not instance._bot:
        instance.init_bot()
    try:
        # set webhook
        webhook_kwargs = {
            'url': instance.null_url
        }
        if instance.enabled:
            webhook = reverse(instance.hook_url, kwargs={'hook_id': instance.hook_id})
            site_domain = getattr(settings, 'MICROBOT_WEBHOOK_DOMAIN', None)
            if site_domain is None:
                site_domain = get_site_domain()
            webhook_kwargs['url'] = 'https://' + site_domain + webhook
            certificate_filename = getattr(settings, 'MICROBOT_WEBHOOK_CERTIFICATE', False)
            if certificate_filename:
                import os
                webhook_kwargs['certificate'] = open(os.path.join(settings.BASE_DIR, certificate_filename), 'rb')
        instance.set_webhook(**webhook_kwargs)
        logger.info("Success: Webhook url %s for bot %s set" % (webhook_kwargs['url'], str(instance)))
    except:
        logger.error("Failure: Webhook url %s for bot %s not set" % (webhook_kwargs['url'], str(instance)))
        raise
    
def set_bot_api_data(sender, instance, **kwargs):
        #  set bot api if not yet
    if not instance._bot:
        instance.init_bot()
    
    try:
        #  complete  Bot instance with api data
        if not instance.user_api:
            bot_api = instance._bot.get_me()
            User = apps.get_model('permabots', 'User')
            user_dict = bot_api.to_dict()
            user_dict.pop('is_bot', None)
            user_api, _ = User.objects.get_or_create(**user_dict)
            instance.user_api = user_api
            logger.info("Success: Bot api info for bot %s set" % str(instance))
    except:
        logger.error("Failure: Bot api info for bot %s no set" % str(instance))
        raise  
    
def validate_bot(sender, instance, **kwargs):
    validate_token(instance.token)
    
def delete_cache(sender, instance, **kwargs):
    caching.delete(sender, instance)
    
def delete_cache_env_vars(sender, instance, **kwargs):
    caching.delete(instance.bot._meta.model, instance.bot, 'env_vars')
    
def delete_cache_handlers(sender, instance, **kwargs):
    caching.delete(instance.bot._meta.model, instance.bot, 'handlers')
    
def delete_cache_source_states(sender, instance, **kwargs):
    caching.delete(instance._meta.model, instance, 'source_states')
    
def delete_bot_integrations(sender, instance, **kwargs):
    if instance.telegram_bot:
        instance.telegram_bot.delete()
    if instance.kik_bot:
        instance.kik_bot.delete()
    if instance.messenger_bot:
        instance.messenger_bot.delete()
