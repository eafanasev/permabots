# -*- coding: utf-8 -*-
# Generated by Django 1.9.4 on 2016-04-03 11:30
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('microbot', '0013_auto_20160403_0621'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatstate',
            name='context',
            field=models.TextField(blank=True, help_text='Context serialized to json when this state was set', null=True, verbose_name='Context'),
        ),
    ]