## TODO

- Sorting of bookmarks
  - Sort by title
  - Sort by date
- Logging of actions
- Change tags to the MaterializeCSS tags: http://materializecss.com/chips.html
- Do calls to the API endpoint of an existing bookmark when editing properties
  (for example to update tags, title and such, also to already suggest title)
- Look into compatibility with del.icio.us, so we can make use of existing browser integration


## v1.1.0 (unreleased)

- Removed some dependencies

## v1.0.0

2016-12-29

- json view of public tag pages, returns all items
- feed (rss/atom) view of public tag pages, returns latest 15
- feed link on public tag page
- Support for bookmarklets
- UI tweaks
- Redesigned cards with bigger favicon. Looks cleaner
- Different favicon service with 60x60px icons
- Prevent duplicate form submission on add/edit bookmark
- Delete bookmark from bookmark card
- Undo delete link in "Bookmark has been deleted" message
- Delete public tag page
- On tags overview page:
  - Show which tags have public pages, with link
  - How many bookmarks each tag has
  - Statistics on:
    - total tags
    - number of public tag pages
    - total number of bookmarks
    - number of starred bookmarks
    - number of bookmarks with a non-OK http status
    - number of deleted bookmarks
- Filter on 'star' status, 'broken' status (non-http-200-OK)
- Bookmark can have a note now
  - Note icon on card with text in title (desktop browser)
  - Filter on bookmarks with a note
- Show url domain name along with 'no title' for items without title
- Catch connection timeouts and such
- Open in new tab/window, prevent
  http://davidebove.com/blog/2016/05/05/target_blank-the-vulnerability-in-your-browser/
- Put the tag selection in a collapsible element to prevent clutter in edit window
- Updated MaterializeCSS and jQuery


## v0.2.0

2016-08-02

- Favicon courtesy Freepik on flaticon.com
- Tag tags for easy adding of tags
- Updates to MaterializeCSS and jQuery
- Several bug- and code style fixes
- Styling tweaks
- Added 'Add bookmark' FAB to the bookmarks overview
- Option to strip parameters from url (like '?utm_source=social')


## v0.1.0

2016-07-26

- Initial release
- Flask application with functionality to add users, add and edit bookmarks,
  tag bookmarks, group by tags, create tag-based public pages (read-only, to be shared
  with interested parties)
