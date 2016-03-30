#!/usr/bin/env python
# -*- coding: utf-8 -*-
from microbot.models import Bot, Request, EnvironmentVar, Hook, ChatState, Handler
from tests.models import Author, Book
from microbot.test import factories, testcases
from django.core.urlresolvers import reverse
from django.test import LiveServerTestCase
from rest_framework import status
from django.conf import settings
from rest_framework.authtoken.models import Token
from django.apps import apps
from django.core.exceptions import ValidationError
try:
    from unittest import mock
except ImportError:
    import mock  # noqa

ModelUser = apps.get_model(getattr(settings, 'AUTH_USER_MODEL', 'auth.User'))

class TestBot(testcases.BaseTestBot):
       
    def test_enable_webhook(self):
        self.assertTrue(self.bot.enabled)
        with mock.patch("telegram.bot.Bot.setWebhook", callable=mock.MagicMock()) as mock_setwebhook:
            self.bot.save()
            args, kwargs = mock_setwebhook.call_args
            self.assertEqual(1, mock_setwebhook.call_count)
            self.assertIn(reverse('microbot:telegrambot', kwargs={'token': self.bot.token}), 
                          kwargs['webhook_url'])
               
    def test_disable_webhook(self):
        self.bot.enabled = False
        with mock.patch("telegram.bot.Bot.setWebhook", callable=mock.MagicMock()) as mock_setwebhook:
            self.bot.save()
            args, kwargs = mock_setwebhook.call_args
            self.assertEqual(1, mock_setwebhook.call_count)
            self.assertEqual(None, kwargs['webhook_url'])
               
    def test_bot_user_api(self):
        with mock.patch("telegram.bot.Bot.setWebhook", callable=mock.MagicMock()):
            self.bot.user_api = None
            self.bot.save()
            self.assertEqual(self.bot.user_api.first_name, u'Microbot_test')
            self.assertEqual(self.bot.user_api.username, u'Microbot_test_bot')
               
    def test_no_bot_associated(self):
        Bot.objects.all().delete()
        self.assertEqual(0, Bot.objects.count())
        response = self.client.post(self.webhook_url, self.update.to_json(), **self.kwargs)
        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)
          
    def test_bot_disabled(self):
        self.bot.enabled = False
        self.bot.save()
        response = self.client.post(self.webhook_url, self.update.to_json(), **self.kwargs)
        self.assertEqual(status.HTTP_404_NOT_FOUND, response.status_code)        
       
    def test_not_valid_update(self):
        del self.update.message
        response = self.client.post(self.webhook_url, self.update.to_json(), **self.kwargs)
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code)
        
    def test_not_valid_bot_token(self):
        self.assertRaises(ValidationError, Bot.objects.create, token="asdasd")
        
class TestHandler(testcases.BaseTestBot):
    
    author_get = {'in': '/authors',
                  'out': {'parse_mode': 'HTML',
                          'reply_markup': '',
                          'text': '<b>author1</b>'
                          }
                  }
             
    def test_no_handler(self):
        self._test_message(self.author_get, no_handler=True)
         
    def test_handler_disabled(self):
        self.handler = factories.HandlerFactory(bot=self.bot, enabled=False)
        self._test_message(self.author_get, no_handler=True)      
        
    def test_handler_in_other_state(self):
        self.state = factories.StateFactory(bot=self.bot,
                                            name="state1")
        self.handler = factories.HandlerFactory(bot=self.bot)
        self.handler.source_states.add(self.state)
        self.new_state = factories.StateFactory(bot=self.bot,
                                                name="state2")
        self.chat = factories.ChatAPIFactory(id=self.update.message.chat.id,
                                             type=self.update.message.chat.type, 
                                             title=self.update.message.chat.title,
                                             username=self.update.message.chat.username,
                                             first_name=self.update.message.chat.first_name,
                                             last_name=self.update.message.chat.last_name)
        self.chat_state = factories.ChatStateFactory(chat=self.chat,
                                                     state=self.new_state)
        
        self._test_message(self.author_get, no_handler=True)
        
    def test_handler_priority(self):
        self.handler1 = factories.HandlerFactory(bot=self.bot,
                                                 name="handler1",
                                                 priority=1)
        self.handler2 = factories.HandlerFactory(bot=self.bot,
                                                 name="handler2",
                                                 priority=2)
        self.assertEqual(Handler.objects.all()[0], self.handler2)
        self.assertEqual(Handler.objects.all()[1], self.handler1)
        
class TestRequests(LiveServerTestCase, testcases.BaseTestBot):
    
    author_get = {'in': '/authors',
                  'out': {'parse_mode': 'HTML',
                          'reply_markup': '',
                          'text': '<b>author1</b>'
                          }
                  }
    
    author_get_pattern = {'in': '/authors@1',
                          'out': {'parse_mode': 'HTML',
                                  'reply_markup': '',
                                  'text': '<b>author1</b>'
                                  }
                          }
    
    author_get_keyboard = {'in': '/authors',
                           'out': {'parse_mode': 'HTML',
                                   'reply_markup': 'author1',
                                   'text': '<b>author1</b>'
                                   }
                           }
    
    author_post_pattern = {'in': '/authors',
                           'out': {'parse_mode': 'HTML',
                                   'reply_markup': '',
                                   'text': '<b>author1</b> created'
                                   }
                           }
    
    author_put_pattern = {'in': '/authors@1',
                          'out': {'parse_mode': 'HTML',
                                  'reply_markup': '',
                                  'text': '<b>author2</b> updated'
                                  }
                          }
    
    author_delete_pattern = {'in': '/authors_delete@1',
                             'out': {'parse_mode': 'HTML',
                                     'reply_markup': '',
                                     'text': 'Author 1 deleted'
                                     }
                             }
    
    author_get_with_environment_var = {'in': '/authors',
                                       'out': {'parse_mode': 'HTML',
                                               'reply_markup': '',
                                               'text': 'myebookshop:<b>author1</b>'
                                               }
                                       }
    
    author_get_with_url_parameters = {'in': '/authors_name@author1',
                                      'out': {'parse_mode': 'HTML',
                                              'reply_markup': '',
                                              'text': '<b>author1</b>'
                                              }
                                      }
    
    author_post_header_error = {'in': '/authors',
                                'out': {'parse_mode': 'HTML',
                                        'reply_markup': '',
                                        'text': 'not created'
                                        }
                                }
    
    book_get_authorized = {'in': '/books',
                           'out': {'parse_mode': 'HTML',
                                   'reply_markup': '',
                                   'text': '<b>ebook1</b>'
                                   }
                           }
    
    book_get_not_authorized = {'in': '/books',
                               'out': {'parse_mode': 'HTML',
                                       'reply_markup': '',
                                       'text': 'not books'
                                       }
                               }
    
    author_post_data_template = {'in': '/authorscreate@author2',
                                 'out': {'parse_mode': 'HTML',
                                         'reply_markup': '',
                                         'text': '<b>author2</b> created'
                                         }
                                 }
    
    author_put_data_template = {'in': '/authorsupdate@1@author2',
                                'out': {'parse_mode': 'HTML',
                                        'reply_markup': '',
                                        'text': '<b>author2</b> updated'
                                        }
                                }
    
    update_as_part_of_context = {'in': '/authors@1',
                                 'out': {'parse_mode': 'HTML',
                                         'reply_markup': '',
                                         'text': '<b>author2</b> updated by first_name_'
                                         }
                                 }
    
    no_request = {'in': '/norequest',
                  'out': {'parse_mode': 'HTML',
                          'reply_markup': '',
                          'text': 'Just plain response'
                          }
                  }
    
    def test_get_request(self):
        Author.objects.create(name="author1")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/',
                                                method=Request.GET)
        self.response = factories.ResponseFactory(text_template='{% for author in response.list %}<b>{{author.name}}</b>{% endfor %}',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.author_get)
   
    def test_get_pattern_command(self):
        Author.objects.create(name="author1")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/{{url.id}}/',
                                                method=Request.GET)
        self.response = factories.ResponseFactory(text_template='<b>{{response.name}}</b>',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors@(?P<id>\d+)',
                                                response=self.response,
                                                request=self.request)
        self._test_message(self.author_get_pattern)
          
    def test_get_request_with_keyboard(self):
        Author.objects.create(name="author1")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/',
                                                method=Request.GET)
        self.response = factories.ResponseFactory(text_template='{% for author in response.list %}<b>{{author.name}}</b>{% endfor %}',
                                                  keyboard_template='[[{% for author  in response.list %}"{{author.name}}"{% endfor %}]]')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.author_get_keyboard)
      
    def test_post_request(self):
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/',
                                                method=Request.POST,
                                                data='{"name": "author1"}')
        self.response = factories.ResponseFactory(text_template='<b>{{response.name}}</b> created',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.author_post_pattern)
        self.assertEqual(Author.objects.count(), 1)
        author = Author.objects.all()[0]
        self.assertEqual(author.name, "author1")
          
    def test_put_request(self):
        author = Author.objects.create(name="author1")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/{{url.id}}/',
                                                method=Request.PUT,
                                                data='{"name": "author2"}')
        self.response = factories.ResponseFactory(text_template='<b>{{response.name}}</b> updated',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors@(?P<id>\d+)',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.author_put_pattern)
        self.assertEqual(Author.objects.count(), 1)
        author = Author.objects.all()[0]
        self.assertEqual(author.name, "author2")
          
    def test_delete_request(self):
        Author.objects.create(name="author1")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/{{url.id}}/',
                                                method=Request.DELETE)
        self.response = factories.ResponseFactory(text_template='Author {{ url.id }} deleted',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors_delete@(?P<id>\d+)',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.author_delete_pattern)
        self.assertEqual(Author.objects.count(), 0)
  
    def test_environment_vars(self):
        EnvironmentVar.objects.create(bot=self.bot,
                                      key="shop", 
                                      value="myebookshop")
        Author.objects.create(name="author1")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/',
                                                method=Request.GET)
        self.response = factories.ResponseFactory(text_template='{{env.shop}}:{% for author in response.list %}<b>{{author.name}}</b>{% endfor %}',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.author_get_with_environment_var)
         
    def test_url_parameters(self):
        Author.objects.create(name="author1")
        Author.objects.create(name="author2")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/',
                                                method=Request.GET)
        self.url_param = factories.UrlParamFactory(request=self.request,
                                                   key='name',
                                                   value_template='{{url.name}}')
        self.response = factories.ResponseFactory(text_template='{% for author in response.list %}<b>{{author.name}}</b>{% endfor %}',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors_name@(?P<name>\w+)',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.author_get_with_url_parameters)
        
    def test_header_parameters(self):
        # Unsupported media type 415. Author not created
        EnvironmentVar.objects.create(bot=self.bot,
                                      key="content_type", 
                                      value="application/xml")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/',
                                                method=Request.POST,
                                                data='{"name": "author1"}')
        self.header_param = factories.HeaderParamFactory(request=self.request,
                                                         key='Content-Type',
                                                         value_template='{{env.content_type}}')
        self.response = factories.ResponseFactory(text_template='{% if response.name %}<b>{{response.name}}</b> created{% else %}not created{% endif %}',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.author_post_header_error)
        self.assertEqual(Author.objects.count(), 0)
        
    def test_header_authentitcation(self):
        user = ModelUser.objects.create_user(username='username',
                                             email='username@test.com',
                                             password='password')
        token = Token.objects.get(user=user)
        Book.objects.create(title="ebook1", owner=user)
        EnvironmentVar.objects.create(bot=self.bot,
                                      key="token", 
                                      value=token)
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/books/',
                                                method=Request.GET)
        self.header_param = factories.HeaderParamFactory(request=self.request,
                                                         key='Authorization',
                                                         value_template='Token {{env.token}}')
        self.response = factories.ResponseFactory(text_template='''{% if response.list %}{% for book in response.list %}<b>{{book.title}}</b>{% endfor %}
                                                                {% else %}not books{% endif %}''',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(
            bot=self.bot,
            pattern='/books',
            request=self.request,
            response=self.response)
        self._test_message(self.book_get_authorized)
        
    def test_header_not_authenticated(self):
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/books/',
                                                method=Request.GET)
        self.header_param = factories.HeaderParamFactory(request=self.request,
                                                         key='Authorization',
                                                         value_template='Token erroneustoken')
        self.response = factories.ResponseFactory(text_template='''{% if response.list %}{% for book in response.list %}<b>{{book.title}}</b>{% endfor %}
                                                                {% else %}not books{% endif %}''',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(
            bot=self.bot,
            pattern='/books',
            request=self.request,
            response=self.response)
        self._test_message(self.book_get_not_authorized)   
        
    def test_post_data_template(self):
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/',
                                                method=Request.POST,
                                                data='{"name":"{{url.name}}"}')
        self.response = factories.ResponseFactory(text_template='<b>{{response.name}}</b> created',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authorscreate@(?P<name>\w+)',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.author_post_data_template)
        self.assertEqual(Author.objects.all()[0].name, 'author2')
        
    def test_put_data_template(self):
        Author.objects.create(name="author1")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/{{url.id}}/',
                                                method=Request.PUT,
                                                data='{"name":"{{url.name}}"}')
        self.response = factories.ResponseFactory(text_template='<b>{{response.name}}</b> updated',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authorsupdate@(?P<id>\d+)@(?P<name>\w+)',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.author_put_data_template)
        self.assertEqual(Author.objects.all()[0].name, 'author2')
        
    def test_update_as_part_of_context(self):
        Author.objects.create(name="author1")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/{{url.id}}/',
                                                method=Request.PUT,
                                                data='{"name": "author2"}')
        self.response = factories.ResponseFactory(text_template='<b>{{response.name}}</b> updated by {{update.message.from_user.first_name}}',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors@(?P<id>\d+)',
                                                request=self.request,
                                                response=self.response)
        self._test_message(self.update_as_part_of_context)
        self.assertEqual(Author.objects.count(), 1)
        author = Author.objects.all()[0]
        self.assertEqual(author.name, "author2")
        
    def test_handler_with_state(self):
        Author.objects.create(name="author1")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/',
                                                method=Request.GET)
        self.response = factories.ResponseFactory(text_template='{% for author in response.list %}<b>{{author.name}}</b>{% endfor %}',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors',
                                                request=self.request,
                                                response=self.response)
        self.state = factories.StateFactory(bot=self.bot,
                                            name="state1")
        self.state_target = factories.StateFactory(bot=self.bot,
                                                   name="state2")
        self.handler.target_state = self.state_target
        self.handler.save()
        self.handler.source_states.add(self.state)
        self.chat = factories.ChatAPIFactory(id=self.update.message.chat.id,
                                             type=self.update.message.chat.type, 
                                             title=self.update.message.chat.title,
                                             username=self.update.message.chat.username,
                                             first_name=self.update.message.chat.first_name,
                                             last_name=self.update.message.chat.last_name)
        self.chat_state = factories.ChatStateFactory(chat=self.chat,
                                                     state=self.state)
        
        self._test_message(self.author_get)
        self.assertEqual(ChatState.objects.get(chat=self.chat).state, self.state_target)
        
    def test_get_request_with_more_priority(self):
        Author.objects.create(name="author1")
        self.request = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/',
                                                method=Request.GET)
        self.request_priority = factories.RequestFactory(url_template=self.live_server_url + '/api/authors/',
                                                         method=Request.GET)
        self.response = factories.ResponseFactory(text_template='Impossible template',
                                                  keyboard_template='')
        self.response_priority = factories.ResponseFactory(text_template='{% for author in response.list %}<b>{{author.name}}</b>{% endfor %}',
                                                           keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/authors',
                                                request=self.request,
                                                response=self.response,
                                                priority=1)
        self.handler_priority = factories.HandlerFactory(bot=self.bot,
                                                         pattern='/authors',
                                                         request=self.request_priority,
                                                         response=self.response_priority,
                                                         priority=2)
        self._test_message(self.author_get)
        
    def test_no_request(self):
        self.response = factories.ResponseFactory(text_template='Just plain response',
                                                  keyboard_template='')
        self.handler = factories.HandlerFactory(bot=self.bot,
                                                pattern='/norequest',
                                                response=self.response)        
        self._test_message(self.no_request)
        
class TestHook(testcases.BaseTestBot):   
    
    hook_name = {'in': 'key1',
                 'out': {'parse_mode': 'HTML',
                         'reply_markup': 'juan',
                         'text': '<b>juan</b>'
                         }
                 }
    
    hook_keyboard = {'in': 'key1',
                     'out': {'parse_mode': 'HTML',
                             'reply_markup': 'Go back',
                             'text': '<b>juan</b>'
                             }
                     }
    
    def setUp(self):
        super(TestHook, self).setUp()        
        EnvironmentVar.objects.create(bot=self.bot,
                                      key="back", 
                                      value="Go back")
        self.response = factories.ResponseFactory(text_template='<b>{{data.name}}</b>',
                                                  keyboard_template='[["{{data.name}}"]]')
        self.hook = factories.HookFactory(bot=self.bot,
                                          key="key1",
                                          response=self.response)
        self.recipient = factories.RecipientFactory(hook=self.hook)
        
    def test_generate_key(self):
        new_response = factories.ResponseFactory(text_template='<b>{{data.name}}</b>',
                                                 keyboard_template='[["{{data.name}}"]]')
        hook = Hook.objects.create(bot=self.bot,
                                   response=new_response)
        self.assertNotEqual(None, hook.key)
             
    def test_no_hook(self):
        self._test_hook({'in': "keynotfound"}, {}, no_hook=True, auth=self._gen_token(self.bot.owner.auth_token))
        
    def test_hook_disabled(self):
        self.hook.enabled = False
        self.hook.save()
        self._test_hook(self.hook_name, '{"name": "juan"}', no_hook=True,
                        auth=self._gen_token(self.hook.bot.owner.auth_token))
        
    def test_hook(self):
        self._test_hook(self.hook_name, '{"name": "juan"}', num_recipients=1, recipients=[self.recipient.chat_id],
                        auth=self._gen_token(self.hook.bot.owner.auth_token))
        
    def test_hook_keyboard(self):
        self.response.keyboard_template = [["{{data.name}}"], ["{{env.back}}"]]
        self.response.save()
        self._test_hook(self.hook_keyboard, '{"name": "juan"}', num_recipients=1, recipients=[self.recipient.chat_id],
                        auth=self._gen_token(self.hook.bot.owner.auth_token))
        
    def test_hook_multiple_recipients(self):
        new_recipient = factories.RecipientFactory(hook=self.hook)
        self._test_hook(self.hook_name, '{"name": "juan"}', num_recipients=2, recipients=[self.recipient.chat_id, new_recipient.chat_id],
                        auth=self._gen_token(self.hook.bot.owner.auth_token))
        
    def test_not_auth(self):
        self._test_hook(self.hook_name, '{"name": "juan"}', num_recipients=1, recipients=[self.recipient.chat_id],
                        auth=self._gen_token("notoken"), status_to_check=status.HTTP_401_UNAUTHORIZED)