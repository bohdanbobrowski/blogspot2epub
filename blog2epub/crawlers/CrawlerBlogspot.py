#!/usr/bin/env python3
# -*- coding : utf-8 -*-
from blog2epub.crawlers.Crawler import Crawler

class CrawlerBlogspot(Crawler):
    """
    Blogspot.com crawler.   
    """

    images_regex = r'<table[^>]*><tbody>[\s]*<tr><td[^>]*><a href="([^"]*)"[^>]*><img[^>]*></a></td></tr>[\s]*<tr><td class="tr-caption" style="[^"]*">([^<]*)'
    articles_regex = r'<h3 class=\'post-title entry-title\' itemprop=\'name\'>[\s]*<a href=\'([^\']*)\'>([^>^<]*)</a>[\s]*</h3>'
    
