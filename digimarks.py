from __future__ import print_function

import datetime
import gzip
import hashlib
import os
import shutil
import sys

import bs4
import requests
from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   url_for)
from peewee import *  # noqa
from werkzeug.contrib.atom import AtomFeed

from digimarks import models, themes, views

try:
    # Python 3
    from urllib.parse import urljoin, urlparse, urlunparse
except ImportError:
    # Python 2
    from urlparse import urljoin, urlparse, urlunparse


DIGIMARKS_USER_AGENT = 'digimarks/1.2.0-dev'

try:
    import settings
except ImportError:
    print('Copy settings_example.py to settings.py and set the configuration to your own preferences')
    sys.exit(1)

# app configuration
APP_ROOT = os.path.dirname(os.path.realpath(__file__))
MEDIA_ROOT = os.path.join(APP_ROOT, 'static')
MEDIA_URL = '/static/'

# create our flask app and a database wrapper
app = Flask(__name__)
app.config.from_object(__name__)

# Strip unnecessary whitespace due to jinja2 codeblocks
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

# set custom url for the app, for example '/bookmarks'
try:
    app.config['APPLICATION_ROOT'] = settings.APPLICATION_ROOT
except AttributeError:
    pass

# Cache the tags
all_tags = {}
usersettings = {}


def get_cached_tags(userkey):
    """ Fail-safe way to get the cached tags for `userkey` """
    try:
        return all_tags[userkey]
    except KeyError:
        return []


def get_theme(userkey):
    try:
        usertheme = usersettings[userkey]['theme']
        return themes[usertheme]
    except KeyError:
        return themes[DEFAULT_THEME]  # default


def make_external(url):
    return urljoin(request.url_root, url)


def _find_bookmarks(userkey, filter_text):
    return Bookmark.select().where(
        Bookmark.userkey == userkey,
        (
            Bookmark.title.contains(filter_text) |
            Bookmark.url.contains(filter_text) |
            Bookmark.note.contains(filter_text)
        ),
        Bookmark.status == Bookmark.VISIBLE
    ).order_by(Bookmark.created_date.desc())


@app.errorhandler(404)
def page_not_found(e):
    theme = themes[DEFAULT_THEME]
    return render_template('404.html', error=e, theme=theme), 404


@app.route('/')
def index():
    """ Homepage, point visitors to project page """
    theme = themes[DEFAULT_THEME]
    return render_template('index.html', theme=theme)


def get_bookmarks(userkey, filtermethod=None, sortmethod=None):
    """ User homepage, list their bookmarks, optionally filtered and/or sorted """
    #return object_list('bookmarks.html', Bookmark.select())
    #user = User.select(key=userkey)
    #if user:
    #    bookmarks = Bookmark.select(User=user)
    #    return render_template('bookmarks.html', bookmarks)
    #else:
    #    abort(404)
    message = request.args.get('message')
    bookmarktags = get_cached_tags(userkey)

    filter_text = ''
    if request.form:
        filter_text = request.form['filter_text']

    filter_starred = False
    if filtermethod and filtermethod.lower() == 'starred':
        filter_starred = True

    filter_broken = False
    if filtermethod and filtermethod.lower() == 'broken':
        filter_broken = True

    filter_note = False
    if filtermethod and filtermethod.lower() == 'note':
        filter_note = True

    if filter_text:
        bookmarks = _find_bookmarks(userkey, filter_text)
    elif filter_starred:
        bookmarks = Bookmark.select().where(Bookmark.userkey == userkey,
                                            Bookmark.starred).order_by(Bookmark.created_date.desc())
    elif filter_broken:
        bookmarks = Bookmark.select().where(Bookmark.userkey == userkey,
                                            Bookmark.http_status != 200).order_by(Bookmark.created_date.desc())
    elif filter_note:
        bookmarks = Bookmark.select().where(Bookmark.userkey == userkey,
                                            Bookmark.note != '').order_by(Bookmark.created_date.desc())
    else:
        bookmarks = Bookmark.select().where(
            Bookmark.userkey == userkey,
            Bookmark.status == Bookmark.VISIBLE
        ).order_by(Bookmark.created_date.desc())

    return bookmarks, bookmarktags, filter_text, message


@app.route('/<userkey>', methods=['GET', 'POST'])
@app.route('/<userkey>/filter/<filtermethod>', methods=['GET', 'POST'])
@app.route('/<userkey>/sort/<sortmethod>', methods=['GET', 'POST'])
@app.route('/<userkey>/<show_as>', methods=['GET', 'POST'])
@app.route('/<userkey>/<show_as>/filter/<filtermethod>', methods=['GET', 'POST'])
@app.route('/<userkey>/<show_as>/sort/<sortmethod>', methods=['GET', 'POST'])
def bookmarks_page(userkey, filtermethod=None, sortmethod=None, show_as='cards'):
    bookmarks, bookmarktags, filter_text, message = get_bookmarks(userkey, filtermethod, sortmethod)
    theme = get_theme(userkey)
    return render_template(
        'bookmarks.html',
        bookmarks=bookmarks,
        userkey=userkey,
        tags=bookmarktags,
        filter_text=filter_text,
        message=message,
        theme=theme,
        editable=True,  # bookmarks can be edited
        showtags=True,  # tags should be shown with the bookmarks
        filtermethod=filtermethod,
        sortmethod=sortmethod,
        show_as=show_as,  # show list of bookmarks instead of cards
    )


@app.route('/<userkey>/js')
def bookmarks_js(userkey):
    """ Return list of bookmarks with their favicons, to be used for autocompletion """
    bookmarks = Bookmark.select().where(
        Bookmark.userkey == userkey,
        Bookmark.status == Bookmark.VISIBLE
    ).order_by(Bookmark.created_date.desc())
    return render_template(
        'bookmarks.js',
        bookmarks=bookmarks
    )


@app.route('/r/<userkey>/<urlhash>')
def bookmark_redirect(userkey, urlhash):
    """ Securely redirect a bookmark to its url, stripping referrer (if browser plays nice) """
    # @TODO: add counter to this bookmark
    try:
        bookmark = Bookmark.get(
            Bookmark.url_hash == urlhash,
            Bookmark.userkey == userkey,
            Bookmark.status == Bookmark.VISIBLE
        )
    except Bookmark.DoesNotExist:
        abort(404)
    return render_template('redirect.html', url=bookmark.url)


@app.route('/api/v1/<userkey>', methods=['GET', 'POST'])
@app.route('/api/v1/<userkey>/filter/<filtermethod>', methods=['GET', 'POST'])
@app.route('/api/v1/<userkey>/sort/<sortmethod>', methods=['GET', 'POST'])
def bookmarks_json(userkey, filtermethod=None, sortmethod=None):
    bookmarks, bookmarktags, filter_text, message = get_bookmarks(userkey, filtermethod, sortmethod)

    bookmarkslist = [i.serialize for i in bookmarks]

    the_data = {
        'bookmarks': bookmarkslist,
        'tags': bookmarktags,
        'filter_text': filter_text,
        'message': message,
        'userkey': userkey,
    }
    return jsonify(the_data)


@app.route('/api/v1/<userkey>/<urlhash>')
def bookmark_json(userkey, urlhash):
    """ Serialise bookmark to json """
    try:
        bookmark = Bookmark.get(
            Bookmark.url_hash == urlhash,
            Bookmark.userkey == userkey,
            Bookmark.status == Bookmark.VISIBLE
        )
        return jsonify(bookmark.to_dict())
    except Bookmark.DoesNotExist:
        return jsonify({'message': 'Bookmark not found', 'status': 'error 404'})


@app.route('/api/v1/<userkey>/search/<filter_text>')
def search_bookmark_titles_json(userkey, filter_text):
    """ Serialise bookmark to json """
    bookmarks = _find_bookmarks(userkey, filter_text)
    result = []
    for bookmark in bookmarks:
        result.append(bookmark.to_dict())
    return jsonify(result)


@app.route('/<userkey>/<urlhash>')
@app.route('/<userkey>/<urlhash>/edit')
def editbookmark(userkey, urlhash):
    """ Bookmark edit form """
    # bookmark = getbyurlhash()
    try:
        bookmark = Bookmark.get(Bookmark.url_hash == urlhash, Bookmark.userkey == userkey)
    except Bookmark.DoesNotExist:
        abort(404)
    message = request.args.get('message')
    tags = get_cached_tags(userkey)
    if not bookmark.note:
        # Workaround for when an existing bookmark has a null note
        bookmark.note = ''
    theme = get_theme(userkey)
    return render_template(
        'edit.html',
        action='Edit bookmark',
        userkey=userkey,
        bookmark=bookmark,
        message=message,
        formaction='edit',
        tags=tags,
        theme=theme
    )


@app.route('/<userkey>/add')
def addbookmark(userkey):
    """ Bookmark add form """
    url = request.args.get('url')
    if not url:
        url = ''
    if request.args.get('referrer'):
        url = request.referrer
    bookmark = Bookmark(title='', url=url, tags='')
    message = request.args.get('message')
    tags = get_cached_tags(userkey)
    theme = get_theme(userkey)
    return render_template(
        'edit.html',
        action='Add bookmark',
        userkey=userkey,
        bookmark=bookmark,
        tags=tags,
        message=message,
        theme=theme
    )


def updatebookmark(userkey, urlhash=None):
    """ Add (no urlhash) or edit (urlhash is set) a bookmark """
    title = request.form.get('title')
    url = request.form.get('url')
    tags = request.form.get('tags')
    note = request.form.get('note')
    starred = False
    if request.form.get('starred'):
        starred = True
    strip_params = False
    if request.form.get('strip'):
        strip_params = True

    if url and not urlhash:
        # New bookmark
        bookmark, created = Bookmark.get_or_create(url=url, userkey=userkey)
        if not created:
            message = 'Existing bookmark, did not overwrite with new values'
            return redirect(url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash, message=message))
    elif url:
        # Existing bookmark, get from DB
        bookmark = Bookmark.get(Bookmark.userkey == userkey, Bookmark.url_hash == urlhash)
        # Editing this bookmark, set modified_date to now
        bookmark.modified_date = datetime.datetime.now()
    else:
        # No url was supplied, abort. @TODO: raise exception?
        return None

    bookmark.title = title
    if strip_params:
        url = Bookmark.strip_url_params(url)
    bookmark.url = url
    bookmark.starred = starred
    bookmark.set_tags(tags)
    bookmark.note = note
    bookmark.set_hash()
    #bookmark.fetch_image()
    if not title:
        # Title was empty, automatically fetch it from the url, will also update the status code
        bookmark.set_title_from_source()
    else:
        bookmark.set_status_code()

    if bookmark.http_status == 200 or bookmark.http_status == 202:
        try:
            bookmark.set_favicon()
        except IOError:
            # Icon file could not be saved possibly, don't bail completely
            pass

    bookmark.save()
    return bookmark


@app.route('/<userkey>/adding', methods=['GET', 'POST'])
#@app.route('/<userkey>/adding')
def addingbookmark(userkey):
    """ Add the bookmark from form submit by /add """
    tags = get_cached_tags(userkey)

    if request.method == 'POST':
        bookmark = updatebookmark(userkey)
        if not bookmark:
            return redirect(url_for('addbookmark', userkey=userkey, message='No url provided', tags=tags))
        if type(bookmark).__name__ == 'Response':
            return bookmark
        all_tags[userkey] = get_tags_for_user(userkey)
        return redirect(url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash))
    return redirect(url_for('addbookmark', userkey=userkey, tags=tags))


@app.route('/<userkey>/<urlhash>/editing', methods=['GET', 'POST'])
def editingbookmark(userkey, urlhash):
    """ Edit the bookmark from form submit """

    if request.method == 'POST':
        bookmark = updatebookmark(userkey, urlhash=urlhash)
        all_tags[userkey] = get_tags_for_user(userkey)
        return redirect(url_for('editbookmark', userkey=userkey, urlhash=bookmark.url_hash))
    return redirect(url_for('editbookmark', userkey=userkey, urlhash=urlhash))


@app.route('/<userkey>/<urlhash>/delete', methods=['GET', 'POST'])
def deletingbookmark(userkey, urlhash):
    """ Delete the bookmark from form submit by <urlhash>/delete """
    query = Bookmark.update(status=Bookmark.DELETED).where(Bookmark.userkey == userkey, Bookmark.url_hash == urlhash)
    query.execute()
    query = Bookmark.update(deleted_date=datetime.datetime.now()).where(
        Bookmark.userkey == userkey,
        Bookmark.url_hash == urlhash
    )
    query.execute()
    message = 'Bookmark deleted. <a href="{}">Undo deletion</a>'.format(url_for(
        'undeletebookmark',
        userkey=userkey,
        urlhash=urlhash
    ))
    all_tags[userkey] = get_tags_for_user(userkey)
    return redirect(url_for('bookmarks_page', userkey=userkey, message=message))


@app.route('/<userkey>/<urlhash>/undelete')
def undeletebookmark(userkey, urlhash):
    """ Undo deletion of the bookmark identified by urlhash """
    query = Bookmark.update(status=Bookmark.VISIBLE).where(Bookmark.userkey == userkey, Bookmark.url_hash == urlhash)
    query.execute()
    message = 'Bookmark restored'
    all_tags[userkey] = get_tags_for_user(userkey)
    return redirect(url_for('bookmarks_page', userkey=userkey, message=message))


@app.route('/<userkey>/tags')
def tags_page(userkey):
    """ Overview of all tags used by user """
    tags = get_cached_tags(userkey)
    #publictags = PublicTag.select().where(Bookmark.userkey == userkey)
    alltags = []
    for tag in tags:
        try:
            publictag = PublicTag.get(PublicTag.userkey == userkey, PublicTag.tag == tag)
        except PublicTag.DoesNotExist:
            publictag = None

        total = Bookmark.select().where(
            Bookmark.userkey == userkey,
            Bookmark.tags.contains(tag),
            Bookmark.status == Bookmark.VISIBLE
        ).count()
        alltags.append({'tag': tag, 'publictag': publictag, 'total': total})
    totaltags = len(alltags)
    totalbookmarks = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.status == Bookmark.VISIBLE).count()
    totalpublic = PublicTag.select().where(PublicTag.userkey == userkey).count()
    totalstarred = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.starred).count()
    totaldeleted = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.status == Bookmark.DELETED).count()
    totalnotes = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.note != '').count()
    totalhttperrorstatus = Bookmark.select().where(Bookmark.userkey == userkey, Bookmark.http_status != 200).count()
    theme = get_theme(userkey)
    return render_template(
        'tags.html',
        tags=alltags,
        totaltags=totaltags,
        totalpublic=totalpublic,
        totalbookmarks=totalbookmarks,
        totaldeleted=totaldeleted,
        totalstarred=totalstarred,
        totalhttperrorstatus=totalhttperrorstatus,
        totalnotes=totalnotes,
        userkey=userkey,
        theme=theme
    )


@app.route('/<userkey>/tag/<tag>')
def tag_page(userkey, tag):
    """ Overview of all bookmarks with a certain tag """
    bookmarks = Bookmark.select().where(
        Bookmark.userkey == userkey,
        Bookmark.tags.contains(tag),
        Bookmark.status == Bookmark.VISIBLE
    ).order_by(Bookmark.created_date.desc())
    tags = get_cached_tags(userkey)
    pageheader = 'tag: ' + tag
    message = request.args.get('message')

    try:
        publictag = PublicTag.get(PublicTag.userkey == userkey, PublicTag.tag == tag)
    except PublicTag.DoesNotExist:
        publictag = None

    theme = get_theme(userkey)
    return render_template(
        'bookmarks.html',
        bookmarks=bookmarks,
        userkey=userkey,
        tags=tags,
        tag=tag,
        publictag=publictag,
        action=pageheader,
        message=message,
        theme=theme,
        editable=True,
        showtags=True,
    )


def get_publictag(tagkey):
    """ Return tag and bookmarks in this public tag collection """
    this_tag = PublicTag.get(PublicTag.tagkey == tagkey)
    bookmarks = Bookmark.select().where(
        Bookmark.userkey == this_tag.userkey,
        Bookmark.tags.contains(this_tag.tag),
        Bookmark.status == Bookmark.VISIBLE
    ).order_by(Bookmark.created_date.desc())
    return this_tag, bookmarks


@app.route('/pub/<tagkey>')
def publictag_page(tagkey):
    """ Read-only overview of the bookmarks in the userkey/tag of this PublicTag """
    #this_tag = get_object_or_404(PublicTag.select().where(PublicTag.tagkey == tagkey))
    try:
        this_tag, bookmarks = get_publictag(tagkey)
        theme = themes[DEFAULT_THEME]
        return render_template(
            'publicbookmarks.html',
            bookmarks=bookmarks,
            tag=this_tag.tag,
            action=this_tag.tag,
            tagkey=tagkey,
            theme=theme
        )
    except PublicTag.DoesNotExist:
        abort(404)


@app.route('/api/v1/pub/<tagkey>')
def publictag_json(tagkey):
    """ json representation of the Read-only overview of the bookmarks in the userkey/tag of this PublicTag """
    try:
        this_tag, bookmarks = get_publictag(tagkey)
        result = {
            #'tag': this_tag,
            'tagkey': tagkey,
            'count': len(bookmarks),
            'items': [],
        }
        for bookmark in bookmarks:
            result['items'].append(bookmark.to_dict())
        return jsonify(result)
    except PublicTag.DoesNotExist:
        abort(404)


@app.route('/pub/<tagkey>/feed')
def publictag_feed(tagkey):
    """ rss/atom representation of the Read-only overview of the bookmarks in the userkey/tag of this PublicTag """
    try:
        this_tag = PublicTag.get(PublicTag.tagkey == tagkey)
        bookmarks = Bookmark.select().where(
            Bookmark.userkey == this_tag.userkey,
            Bookmark.tags.contains(this_tag.tag),
            Bookmark.status == Bookmark.VISIBLE
        )
        feed = AtomFeed(this_tag.tag, feed_url=request.url, url=make_external(url_for('publictag_page', tagkey=tagkey)))
        for bookmark in bookmarks:
            updated_date = bookmark.modified_date
            if not bookmark.modified_date:
                updated_date = bookmark.created_date
            bookmarktitle = '{} (no title)'.format(bookmark.url)
            if bookmark.title:
                bookmarktitle = bookmark.title
            feed.add(
                bookmarktitle,
                content_type='html',
                author='digimarks',
                url=bookmark.url,
                updated=updated_date,
                published=bookmark.created_date
            )
        return feed.get_response()
    except PublicTag.DoesNotExist:
        abort(404)


@app.route('/<userkey>/<tag>/makepublic', methods=['GET', 'POST'])
def addpublictag(userkey, tag):
    #user = get_object_or_404(User.get(User.key == userkey))
    try:
        User.get(User.key == userkey)
    except User.DoesNotExist:
        abort(404)
    try:
        publictag = PublicTag.get(PublicTag.userkey == userkey, PublicTag.tag == tag)
    except PublicTag.DoesNotExist:
        publictag = None
    if not publictag:
        newpublictag = PublicTag()
        newpublictag.generate_key()
        newpublictag.userkey = userkey
        newpublictag.tag = tag
        newpublictag.save()

        message = 'Public link to this tag created'
        return redirect(url_for('tag_page', userkey=userkey, tag=tag, message=message))

    message = 'Public link already existed'
    return redirect(url_for('tag_page', userkey=userkey, tag=tag, message=message))


@app.route('/<userkey>/<tag>/removepublic/<tagkey>', methods=['GET', 'POST'])
def removepublictag(userkey, tag, tagkey):
    q = PublicTag.delete().where(PublicTag.userkey == userkey, PublicTag.tag == tag, PublicTag.tagkey == tagkey)
    q.execute()
    message = 'Public link deleted'
    return redirect(url_for('tag_page', userkey=userkey, tag=tag, message=message))


@app.route('/<systemkey>/adduser')
def adduser(systemkey):
    """ Add user endpoint, convenience """
    if systemkey == settings.SYSTEMKEY:
        newuser = User()
        newuser.generate_key()
        newuser.username = 'Nomen Nescio'
        newuser.save()
        all_tags[newuser.key] = []
        return redirect('/{}'.format(newuser.key.decode("utf-8")), code=302)
    else:
        abort(404)


@app.route('/<systemkey>/refreshfavicons')
def refreshfavicons(systemkey):
    """ Add user endpoint, convenience """
    if systemkey == settings.SYSTEMKEY:
        bookmarks = Bookmark.select()
        for bookmark in bookmarks:
            if bookmark.favicon:
                try:
                    filename = os.path.join(MEDIA_ROOT, 'favicons/' + bookmark.favicon)
                    os.remove(filename)
                except OSError as e:
                    print(e)
            bookmark.set_favicon()
        return redirect('/')
    else:
        abort(404)


@app.route('/<systemkey>/findmissingfavicons')
def findmissingfavicons(systemkey):
    """ Add user endpoint, convenience """
    if systemkey == settings.SYSTEMKEY:
        bookmarks = Bookmark.select()
        for bookmark in bookmarks:
            try:
                if not bookmark.favicon or not os.path.isfile(os.path.join(MEDIA_ROOT, 'favicons/' + bookmark.favicon)):
                    # This favicon is missing
                    # Clear favicon, so fallback can be used instead of showing a broken image
                    bookmark.favicon = None
                    bookmark.save()
                    # Try to fetch and save new favicon
                    bookmark.set_favicon()
                    bookmark.save()
            except OSError as e:
                print(e)
        return redirect('/')
    else:
        abort(404)


# Initialisation == create the bookmark, user and public tag tables if they do not exist
Bookmark.create_table(True)
User.create_table(True)
PublicTag.create_table(True)

users = User.select()
print('Current user keys:')
for user in users:
    all_tags[user.key] = get_tags_for_user(user.key)
    usersettings[user.key] = {'theme': user.theme}
    print(user.key)

# Run when called standalone
if __name__ == '__main__':
    # run the application
    app.run(host='0.0.0.0', port=9999, debug=True)
