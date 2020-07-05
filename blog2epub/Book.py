#!/usr/bin/env python3
# -*- coding : utf-8 -*-
from dateutil.parser import parse
import os
import tempfile
import zipfile
import locale

from ebooklib import epub
from blog2epub.Cover import Cover


class Book(object):
    """
    Book class used in Blogspot2Epub class.
    """

    style = """
    @namespace epub "http://www.idpf.org/2007/ops";
    body {
        font-family: Cambria, Liberation Serif, Bitstream Vera Serif, Georgia, Times, Times New Roman, serif;
    }
    h2 {
         text-align: left;
         text-transform: uppercase;
         font-weight: 200;     
    }
    ol {
            list-style-type: none;
    }
    ol > li:first-child {
            margin-top: 0.3em;
    }
    nav[epub|type~='toc'] > ol > li > ol  {
        list-style-type:square;
    }
    nav[epub|type~='toc'] > ol > li > ol > li {
            margin-top: 0.3em;
    }
    """

    cover_html = """<?xml version='1.0' encoding='utf-8'?>
    <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
    <head>
    <meta name="calibre:cover" content="true"/>
    <title>Cover</title>
    <style type="text/css" title="override_css">
    @page {
        padding: 0pt;
        margin: 0pt;
    }
    body {
        text-align: center;
        padding: 0pt;
        margin: 0pt;
    }
    </style>
    </head>
    <body>
    <div><svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="100%" height="100%" viewBox="0 0 600 800" preserveAspectRatio="none">
    <image id="cover_img" width="600" height="800" xlink:href="###FILE###"/>
    </svg></div>
    </body>
    </html>"""


    def __init__(self, crawler):
        """
        :param crawler: instance of Crawler class
        """
        self.title = crawler.title
        self.description = crawler.description
        self.url = crawler.url
        self.dirs = crawler.dirs
        self.start = crawler.start
        self.end = crawler.end
        self.include_images = crawler.include_images
        self.images = crawler.images
        self.language = crawler.language
        self.interface = crawler.interface
        self._set_locale()
        self.chapters = []
        self.table_of_contents = []
        self.file_name = None
        self.file_name_prefix = crawler.file_name
        self.file_full_path = None
        self.update_file_name()
        self.destination_folder = crawler.destination_folder
        self.cover = None
        self.book = None
        self._add_chapters(crawler.articles)

    def _set_locale(self):
        if self.language:
            self.locale = self.language+'_'+self.language.upper()+'.UTF-8'           
        else:
            self.locale = 'en_US.UTF-8'
        try:
            locale.setlocale(locale.LC_TIME, self.locale)
            self.interface.print("Locale setted as %s" % self.locale)
        except Exception:            
            self.interface.print("Can't set locale to %s" % self.locale)

    def update_file_name(self):
        file_name = self.file_name_prefix        
        if self.start:            
            start_date = self.start.strftime('%Y.%m.%d')
            if self.end and self.start != self.end:
                end_date = self.end.strftime('%Y.%m.%d')
                file_name = file_name + '_' + end_date + '-' + start_date
            else:
                file_name = file_name + '_' + start_date
        self.file_name = file_name + '.epub'

    def _add_chapters(self, articles):
        for article in articles:
            number = len(self.chapters) + 1
            self.chapters.append(Chapter(article, number, self.language))

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

    def _add_cover(self):
        self.cover = Cover(self)
        cover_file_name, cover_file_full_path = self.cover.generate()
        cover_html = self.cover_html.replace('###FILE###', cover_file_name)
        cover_html_fn = 'EPUB/cover.xhtml'
        content_opf_fn = 'EPUB/content.opf'
        with zipfile.ZipFile(self.file_full_path, 'r') as zf:
            content_opf = zf.read(content_opf_fn)
        tmpfd, tmpname = tempfile.mkstemp(dir=os.path.dirname(self.file_full_path))
        os.close(tmpfd)
        with zipfile.ZipFile(self.file_full_path, 'r') as zin:
            with zipfile.ZipFile(tmpname, 'w') as zout:
                zout.comment = zin.comment  # preserve the comment
                for item in zin.infolist():
                    if item.filename not in [cover_html_fn, content_opf_fn]:
                        zout.writestr(item, zin.read(item.filename))
        os.remove(self.file_full_path)
        os.rename(tmpname, self.file_full_path)
        with zipfile.ZipFile(self.file_full_path, 'a') as zf:
            zf.writestr(cover_html_fn, cover_html)
            zf.write(cover_file_full_path, 'EPUB/' + cover_file_name)
            zf.writestr(content_opf_fn, self._upgrade_opf(content_opf, cover_file_name))
        # os.remove(cover_file_full_path)
        try:
            self.interface.notify('blog2epub', 'Epub created', self.file_full_path, cover_file_full_path)
        except Exception:
            if os.path.isfile(self.file_full_path):
                self.interface.print('Epub created: %s' % self.file_full_path)

    def _upgrade_opf(self, content_opt, cover_file_name):
        new_manifest = """<manifest>
    <item href="cover.xhtml" id="cover" media-type="application/xhtml+xml"/>
    <item href="{}" id="cover_img" media-type="image/jpeg"/>""".format(cover_file_name)
        content_opt = content_opt.decode("utf-8").replace("<manifest>", new_manifest)
        return content_opt

    def _add_table_of_contents(self):
        self.table_of_contents.reverse()
        self.book.toc = self.table_of_contents
        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())

    def _add_epub_css(self):
        nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=self.style)
        self.book.add_item(nav_css)

    def _include_images(self):
        images_included = []
        if self.include_images:
            for i, image in enumerate(self.images, start=1):
                if image not in images_included and os.path.isfile(os.path.join(self.dirs.images, image)):
                    epub_img = epub.EpubItem(uid="img%s" % i, file_name="images/" + image, media_type="image/jpeg",
                                             content=open(os.path.join(self.dirs.images, image), 'rb').read())
                    self.book.add_item(epub_img)
                    images_included.append(image)

    def save(self):
        self.update_file_name()
        self.book = epub.EpubBook()
        self.book.set_title(self.title)
        self.book.set_language(self.language)
        self.book.add_author(self.title + ', ' + self.file_name_prefix)
        for chapter in self.chapters:
            self.book.add_item(chapter.epub)
            self.book.spine.append(chapter.epub)
            self.table_of_contents.append(chapter.epub)
        self._add_table_of_contents()
        self._add_epub_css()
        self.book.spine.append('nav')
        self.book.spine.append('cover')
        self.book.spine.reverse()
        if len(self.description) > 0:
            self.book.add_metadata('DC', 'description', "\n".join(self.description))
        self._include_images()
        print(self)
        self.file_full_path = os.path.join(self.destination_folder, self.file_name)
        epub.write_epub(self.file_full_path, self.book, {})
        self._add_cover()


class Chapter(object):

    def __init__(self, article, number, language):
        """
        :param article: Article class
        """
        uid = 'chapter_' + str(number)
        self.epub = epub.EpubHtml(title=article.title, uid=uid, file_name=uid + '.xhtml', lang=language)
        tags = self._print_tags(article)        
        self.epub.content = '<h2>{}</h2>{}{}<p><i><a href="{}">{}</a></i></p>'.format(article.title, tags,        
        article.date.strftime('%d %B %Y, %H:%M'), article.url, article.url)
        self.epub.content = '<div>' + self.epub.content + article.content + article.comments + '</div>'

    def _print_tags(self, article):
        if not article.tags:
            return ""
        tags = []
        for tag in article.tags:
            tags.append('<span epub:type="keyword">' + tag + '<span>')
        return "<h5>{}</h5>".format(', '.join(tags))

        

