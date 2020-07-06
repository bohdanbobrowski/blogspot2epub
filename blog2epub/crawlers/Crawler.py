#!/usr/bin/env python3
# -*- coding : utf-8 -*-
import hashlib
import html
import os
import re
import dateutil.parser
from pathlib import Path
from datetime import datetime
import urllib
import gzip
import requests, pickle
import atoma
from urllib import request
from http.cookiejar import Cookie, CookieJar
from lxml.html import tostring 
from lxml.html.soupparser import fromstring 
from lxml.ElementInclude import etree
from PIL import Image
from fake_useragent import UserAgent

import blog2epub
from blog2epub.Book import Book


class Crawler(object):
    """
    Universal blog crawler.
    """
    
    images_regex = r'<table[^>]*><tbody>[\s]*<tr><td[^>]*><a href="([^"]*)"[^>]*><img[^>]*></a></td></tr>[\s]*<tr><td class="tr-caption" style="[^"]*">([^<]*)'
    articles_regex = r'<h3 class=\'post-title entry-title\' itemprop=\'name\'>[\s]*<a href=\'([^\']*)\'>([^>^<]*)</a>[\s]*</h3>'

    def __init__(self, url, include_images=True, images_height=800, images_width=600, images_quality=40, start=None,
                 end=None, limit=None, skip=False, force_download=False, file_name=None, destination_folder='./',
                 cache_folder=None, language=None, interface=None, **kwargs):
        self.url = Crawler.prepare_url(url)
        self.url_to_crawl = Crawler.prepare_url_to_crawl(self.url)
        self.port = Crawler.prepare_port(self.url_to_crawl)
        self.file_name = Crawler.prepare_file_name(file_name, self.url)
        self.destination_folder = destination_folder
        self.cache_folder = cache_folder
        if cache_folder is None:
            self.cache_folder = os.path.join(str(Path.home()), '.blog2epub')
        self.include_images = include_images
        self.images_quality = images_quality
        self.images_height = images_height
        self.images_width = images_width
        self.start = start
        self.end = end
        self.limit = limit
        self.skip = skip
        self.force_download = force_download
        self.interface = Crawler.get_the_interface(interface)
        self.dirs = Dirs(self.cache_folder, self.url.replace('/', '_'))
        self.book = None
        self.title = None
        self.description = None
        self.language = language
        self.atom_feed = False
        self.articles = []
        self.article_counter = 0
        self.images = []
        self.downloader = Downloader(self)
        self.tags = {}

    @staticmethod
    def prepare_url(url):
        return url.replace('http:', '').replace('https:', '').strip('/')

    @staticmethod
    def prepare_file_name(file_name, url):
        if file_name:
            return file_name
        return url.replace('/', '_')

    @staticmethod
    def prepare_url_to_crawl(url):
        r = request.urlopen('http://' + url)
        return r.geturl()

    @staticmethod
    def prepare_port(url):
        if url.startswith("https://"):
            return 443
        else:
            return 80

    @staticmethod
    def get_the_interface(interface):
        if interface:
            return interface
        else:
            return EmptyInterface()

    def get_cover_title(self):
        cover_title = self.title + ' '
        if self.start == self.end:
            cover_title = cover_title + str(self.start)
        else:
            end_date = self.end.split(' ')
            start_date = self.start.split(' ')
            if len(end_date) == len(start_date):
                ed = []
                for i, d in enumerate(end_date):
                    if d != start_date[i]:
                        ed.append(d)
            ed = ' '.join(ed)
            cover_title = cover_title + ed + '-' + self.start
        return cover_title

    @staticmethod
    def get_date(str_date):
        return re.sub('[^\,]*, ', '', str_date)

    def _set_blog_language(self, content):
        if self.language is None and re.search("'lang':[\s]*'([a-z^']+)'", content):
            self.language = re.search("'lang':[\s]*'([a-z^']+)'", content).group(1).strip()
        if self.language is None and re.search('lang=[\'"]([a-z]+)[\'"]', content):
            self.language = re.search('lang=[\'"]([a-z]+)[\'"]', content).group(1).strip()
        if self.language is None and re.search('locale[\'"]:[\s]*[\'"]([a-z]+)[\'"]', content):
            self.language = re.search('locale[\'"]:[\s]*[\'"]([a-z]+)[\'"]', content).group(1).strip()
        if self.language is None:
            self.language = 'en'

    def _get_blog_title(self, content):
        if re.search("<title>([^>^<]*)</title>", content):
            return re.search("<title>([^>^<]*)</title>", content).group(1).strip()
        return ''

    def _get_blog_description(self, tree):
        return tree.xpath('//div[@id="header"]/div/div/div/p[@class="description"]/span/text()')

    def _get_header_images(self, tree):
        header_images = []
        for img in tree.xpath('//div[@id="header"]/div/div/div/p[@class="description"]/span/img/@src'):
            header_images.append(self.downloader.download_image(img))
        return header_images

    def _get_articles(self, content):
        """
        :param content: web page content
        :return: list of Article class objects
        """
        tree = fromstring(content)
        art_urls = tree.xpath("//h3[contains(@class, 'entry-title')]/a/@href")
        art_titles = tree.xpath("//h3[contains(@class, 'entry-title')]/a/text()")
        output = []
        if art_urls and len(art_urls) == len(art_titles):
            for i in range(len(art_urls)):
                output.append(Article(art_urls[i], art_titles[i], self))
        else:
            articles_list = re.findall(self.articles_regex, content)
            for art in articles_list:
                output.append(Article(art[0], art[1], self))
        if not output:
            # try to load atom
            atom_content = self.downloader.get_content('http://' + self.url + '/feeds/posts/default')
            try:            
                feed = atoma.parse_atom_bytes(bytes(atom_content, encoding="utf-8"))
                self.atom_feed = feed
            except Exception:
                pass
        return output

    def _get_url_to_crawl(self, tree):
        url_to_crawl = None
        if tree.xpath('//a[@class="blog-pager-older-link"]/@href'):
            url_to_crawl = tree.xpath('//a[@class="blog-pager-older-link"]/@href')[0]
        return url_to_crawl

    def _add_tags(self, tags):
        for tag in tags:
            if tag in self.tags:
                self.tags[tag] = self.tags[tag]+1
            else:
                self.tags[tag] = 1

    # TODO: This method should be refactored - atom feed logic should be moved to another crawler
    def _articles_loop(self, content):
        articles = self._get_articles(content)
        if self.atom_feed:
            for item in self.atom_feed.entries:
                self.article_counter += 1
                art = Article(item.links[0].href, item.title.value, self)
                self.interface.print(str(len(self.articles) + 1) + '. ' + art.title)
                art.date = item.updated
                if self.start:
                    self.end = art.date
                else:
                    self.start = art.date
                art.set_content(item.content.value)
                art.get_images()
                art.set_content(art.html)
                self.images = self.images + art.images
                self.articles.append(art)
                self._add_tags(art.tags)
                self._check_limit()                
        elif articles:        
            for art in articles:
                self.article_counter += 1
                if not self.skip or self.article_counter > self.skip:
                    art.process()
                    self.images = self.images + art.images
                    self.interface.print(str(len(self.articles) + 1) + '. ' + art.title)
                    if self.start:
                        self.end = art.date
                    else:
                        self.start = art.date
                    self.articles.append(art)
                    self._add_tags(art.tags)
                    self._check_limit()                
                if not self.url_to_crawl:
                    break

    def _check_limit(self):
        if self.limit and len(self.articles) >= self.limit:
            self.url_to_crawl = None

    def _prepare_content(self, content):
        return content

    def _crawl(self):
        while self.url_to_crawl:
            content = self.downloader.get_content(self.url_to_crawl)

            tree = fromstring(content)
            if len(self.articles) == 0:
                self._set_blog_language(content)
                self.images = self.images +self._get_header_images(tree)
                self.description = self._get_blog_description(tree)
                self.title = self._get_blog_title(content)
            content = self._prepare_content(content)
            self._articles_loop(content)
            self.url_to_crawl = self._get_url_to_crawl(tree)
            self._check_limit()

    def save(self):
        self._crawl()
        self.book = Book(self)
        self.book.save()


class Dirs(object):
    """
    Tiny class to temporary directories configurations.
    """

    def _prepare_directories(self):
        paths = [self.html, self.images, self.originals]
        for p in paths:
            if not os.path.exists(p):
                os.makedirs(p)

    def __init__(self, cache_folder, name):
        self.path = os.path.join(cache_folder, name)
        self.html = os.path.join(self.path, 'html')
        self.images = os.path.join(self.path, 'images')
        self.originals = os.path.join(self.path, 'originals')
        self.assets = os.path.join(str(os.path.realpath(blog2epub.__file__).replace('__init__.py','')), 'assets')
        self._prepare_directories()


class Downloader(object):

    def __init__(self, crawler):
        self.dirs = crawler.dirs
        self.crawler_url = crawler.url
        self.crawler_port = crawler.port
        self.interface = crawler.interface
        self.force_download = crawler.force_download
        self.images_width = crawler.images_width
        self.images_height = crawler.images_height
        self.images_quality = crawler.images_quality
        self.cookies = CookieJar()
        self.session = requests.session()
        ua = UserAgent()
        self.headers = {
            'User-Agent': ua.chrome,
        }

    def get_urlhash(self, url):
        m = hashlib.md5()
        m.update(url.encode('utf-8'))
        return m.hexdigest()

    def file_write(self, contents, filepath):
        filepath = filepath + ".gz"
        with gzip.open(filepath, 'wb') as f:
            f.write(contents.encode('utf-8'))

    def file_read(self, filepath):
        if os.path.isfile(filepath + ".gz"):
            with gzip.open(filepath + ".gz", 'rb') as f:
                contents = f.read().decode('utf-8')
        else:            
            with open(filepath, 'rb') as html_file:
                contents = html_file.read().decode('utf-8')
            self.file_write(contents, filepath)
            os.remove(filepath)
        return contents

    def get_filepath(self, url):
        return os.path.join(self.dirs.html, self.get_urlhash(url) + '.html')

    def file_download(self, url, filepath):
        self.dirs._prepare_directories()                
        response = self.session.get(url, cookies=self.cookies, headers=self.headers)        
        self.cookies = response.cookies
        data = response.content
        try:
            contents = data.decode('utf-8', errors='replace')
        except Exception as e:
            contents = data
            self.interface.print(e)
        self.file_write(contents, filepath)
        return contents

    def image_download(self, url, filepath):
        try:
            self.dirs._prepare_directories()
            f = open(filepath, 'wb')                        
            response = self.session.get(url, cookies=self.cookies, headers=self.headers)        
            f.write(response.content)
            f.close()
            return True
        except Exception:
            return False

    def checkInterstitial(self, contents):
        interstitial = re.findall('interstitial=([^"]+)', contents)        
        if interstitial:
            return interstitial[0]
        else:
            return False

    def get_content(self, url):
        filepath = self.get_filepath(url) 
        if self.force_download or (not os.path.isfile(filepath) and not os.path.isfile(filepath + ".gz")):
            contents = self.file_download(url, filepath)
        else:            
            contents = self.file_read(filepath)
        interstitial = self.checkInterstitial(contents)
        if interstitial:
            interstitial_url = "http://" + self.crawler_url + "?interstitial="+interstitial
            self.file_download(interstitial_url, self.get_filepath(interstitial_url))
            contents = self.file_download("http://" + self.crawler_url, self.get_filepath("http://" + self.crawler_url));
        return contents

    def download_image(self, img):
        if img.startswith("//"):
            img = "http:" + img
        img_hash = self.get_urlhash(img)
        img_type = os.path.splitext(img)[1].lower()
        original_fn = os.path.join(self.dirs.originals, img_hash + "." + img_type)
        resized_fn = os.path.join(self.dirs.images, img_hash + ".jpg")
        if not os.path.isfile(resized_fn) or self.force_download:
            self.image_download(img, original_fn)
        if os.path.isfile(original_fn):
            try:
                picture = Image.open(original_fn)
                if picture.size[0] > self.images_width or picture.size[1] > self.images_height:
                    picture.thumbnail([self.images_width, self.images_height], Image.ANTIALIAS)
                picture = picture.convert('L')
                picture.save(resized_fn, format='JPEG', quality=self.images_quality)
            except Exception:
                return None
            os.remove(original_fn)
        return img_hash + ".jpg"


class Article(object):
    """
    Blog post, article which became book chapter...
    """

    def __init__(self, url, title, crawler):
        self.url = url
        self.title = title
        self.tags = []
        self.interface = crawler.interface
        self.dirs = crawler.dirs
        self.comments = ''
        self.include_images = crawler.include_images
        self.images_regex = crawler.images_regex
        self.language = crawler.language
        self.images = []
        self.images_captions = []
        self.html = None
        self.content = None
        self.date = None
        self.tree = None        
        self.downloader = Downloader(crawler)

    def _get_title(self):
        self.title = html.unescape(self.title.strip())

    def _get_date(self):
        date = self.tree.xpath('//abbr[@itemprop="datePublished"]/@title')
        if date:
            self.date = date[0]
        else:
            date = self.tree.xpath('//h2[@class="date-header"]/span/text()')
            if len(date) > 0:
                self.date = re.sub('(.*?, )', '', date[0])
        if self.date is None:
            d = self.url.split('/')
            if len(d) > 4:
                self.date = "%s-%s-01 00:00" % (d[3], d[4])
            else:
                self.date = str(datetime.now())
        else:
            self.date = self._translate_month(self.date)
        self.date = dateutil.parser.parse(self.date)

    def _translate_month(self, date):
        # TODO: need to be refactored, or moved as parameter to dateutil parser function
        date = date.lower()
        if self.language == 'pl':
            date = date.replace('stycznia', 'january')
            date = date.replace('lutego', 'february')
            date = date.replace('marca', 'march')
            date = date.replace('kwietnia', 'april')
            date = date.replace('maja', 'may')
            date = date.replace('czerwca', 'june')
            date = date.replace('lipca', 'july')
            date = date.replace('sierpnia', 'august')
            date = date.replace('września', 'september')
            date = date.replace('października', 'october')
            date = date.replace('listopada', 'november')
            date = date.replace('grudnia', 'december')
        if self.language == 'ru':
            date = date.replace('января', 'january')
            date = date.replace('февраля', 'february')
            date = date.replace('марта', 'march')
            date = date.replace('апреля', 'april')
            date = date.replace('мая', 'may')
            date = date.replace('июня', 'june')
            date = date.replace('июля', 'july')
            date = date.replace('августа', 'august')
            date = date.replace('сентября', 'september')
            date = date.replace('октября', 'october')
            date = date.replace('ноября', 'november')
            date = date.replace('декабря', 'december')
            date = re.sub(' г.$', '', date)
        return date

    def _find_images(self):
        return re.findall(self.images_regex, self.html)

    @staticmethod
    def _default_ripper(img, img_hash, html):
        im_regex = '<table[^>]*><tbody>[\s]*<tr><td[^>]*><a href="' + img.replace("+", "\+") +\
                   '"[^>]*><img[^>]*></a></td></tr>[\s]*<tr><td class="tr-caption" style="[^"]*">[^<]*</td></tr>[\s]*</tbody></table>'
        try:
            return re.sub(im_regex, ' #blog2epubimage#' + img_hash + '# ', html)
        except Exception as e:
            print(e)

    @staticmethod
    def _nocaption_ripper(img, img_hash, html):
        im_regex = '<a href="' + img.replace("+", "\+") + '" imageanchor="1"[^<]*<img.*?></a>'
        try:
            return re.sub(im_regex, ' #blog2epubimage#' + img_hash + '# ', html)
        except Exception as e:
            print(e)

    @staticmethod
    def _bloggerphoto_ripper(img, img_hash, html):
        im_regex = '<a href="[^"]+"><img.*?id="BLOGGER_PHOTO_ID_[0-9]+".*?src="' + img.replace("+", "\+") + '".*?/a>'
        try:
            return re.sub(im_regex, ' #blog2epubimage#' + img_hash + '# ', html)
        except Exception as e:
            print(e)

    @staticmethod
    def _img_ripper(img, img_hash, html):
        im_regex = '<img.*?src="' + img.replace("+", "\+") + '".*?>'
        try:
            return re.sub(im_regex, ' #blog2epubimage#' + img_hash + '# ', html)
        except Exception as e:
            print(e)

    def _process_images(self, images, ripper):
        for image in images:
            if isinstance(image, str):
                img = image
                caption = ''
            else:
                img = image[0]
                caption = image[1]
            img_hash = self.downloader.download_image(img)
            if img_hash:
                self.html = ripper(img=img, img_hash=img_hash, html=self.html)
                self.images.append(img_hash)
                self.images_captions.append(caption)
        self.get_tree()

    def get_images(self):        
        self._process_images(self._find_images(), self._default_ripper)
        self._process_images(self.tree.xpath('//a[@imageanchor="1"]/@href'), self._nocaption_ripper)
        self._process_images(self.tree.xpath('//img[contains(@id,"BLOGGER_PHOTO_ID_")]/@src'), self._bloggerphoto_ripper)
        self._process_images(self.tree.xpath('//img/@src'), self._img_ripper)
        self._replace_images()
        self.get_tree()

    def set_content(self, content):
        self.content = content
        self.html = content
        self.get_tree()

    def _replace_images(self):
        for key, image in enumerate(self.images):
            image_caption = self.images_captions[key]
            image_html = '<table align="center" cellpadding="0" cellspacing="0" class="tr-caption-container" style="margin-left: auto; margin-right: auto; text-align: center; background: #FFF; box-shadow: 1px 1px 5px rgba(0, 0, 0, 0.5); padding: 8px;"><tbody><tr><td style="text-align: center;"><img border="0" src="images/' + image + '" /></td></tr><tr><td class="tr-caption" style="text-align: center;">' + image_caption + '</td></tr></tbody></table>'
            self.html = self.html.replace('#blog2epubimage#' + image + '#', image_html)

    def _get_content(self):
        self.content = self.tree.xpath("//div[contains(concat(' ',normalize-space(@class),' '),'post-body')]")
        if len(self.content) == 1:
            self.content = self.content[0]
            self.content = etree.tostring(self.content)
            self.content = re.sub('style="[^"]*"', '', self.content.decode("utf-8"))
            self.content = re.sub('class="[^"]*"', '', self.content)
            iframe_srcs = re.findall('<iframe.+? src="([^?= ]*)', self.content)
            for src in iframe_srcs:
                self.content = re.sub('<iframe.+?%s.+?/>' % src, '<a href="%s">%s</a>' % (src, src), self.content)

    def get_tree(self):
        self.tree = fromstring(self.html)

    def _get_tags(self):
        tags = self.tree.xpath('//a[@rel="tag"]//text()')        
        output = []
        for t in tags:
            t = t.strip()
            output.append(t)
        self.tags = output
            
    def _get_comments(self):
        """
        :param article: Article class
        :return:
        """
        headers = self.tree.xpath('//div[@id="comments"]/h4/text()')
        self.comments = ''
        if len(headers) == 1:
            self.comments = '<hr/><h3>' + headers[0] + '</h3>'
        comments_in_article = self.tree.xpath('//div[@class="comment-block"]//text()')
        tag = 'h6'
        for c in comments_in_article:
            c = c.strip()
            if c != 'Odpowiedz' and c != 'Usuń':
                self.comments = self.comments + '<' + tag + '>' + c + '</' + tag + '>'
                if tag == 'h6': tag = 'p'
            if c == 'Usuń': tag = 'h6'

    def process(self):
        self.html = self.downloader.get_content(self.url)
        self.get_tree()
        self._get_title()
        self._get_date()
        self.get_images()
        self._get_tags()
        self._get_content()
        self._get_comments()


class EmptyInterface(object):
    """
    Emty interface for script output.
    """

    @staticmethod
    def print(self):
        pass

    @staticmethod
    def exception(e):
        pass