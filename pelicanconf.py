#!/usr/bin/env python
# -*- coding: utf-8 -*- #
from __future__ import unicode_literals

AUTHOR = 'bambalaam'
SITENAME = 'BamBalaam'
SITEURL = ''

PATH = 'content'

TIMEZONE = 'Europe/Brussels'

DEFAULT_LANG = 'en'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

DEFAULT_PAGINATION = 5
DISPLAY_PAGES_ON_MENU = True

# Uncomment following line if you want document-relative URLs when developing
#RELATIVE_URLS = True

THEME = "themes/pelican-alchemy/alchemy"
SITEIMAGE = 'images/avatar.png'

FOOTER_LINKS = [("Source", "https://github.com/BamBalaam/bambalaam.github.io")]
THEME_CSS_OVERRIDES = ['theme/css/oldstyle.css']

ICONS = (
    ('github', 'https://github.com/BamBalaam'),
    ('linkedin', 'https://linkedin.com/in/andremadeiracortes'),
)
