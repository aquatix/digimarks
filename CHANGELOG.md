# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).


## TODO

- Sorting of bookmarks
  - Sort by title
  - Sort by date
- Logging of actions
- Change tags to the MaterializeCSS tags: http://materializecss.com/chips.html
- Do calls to the API endpoint of an existing bookmark when editing properties
  (for example to update tags, title and such, also to already suggest title)
- Look into compatibility with del.icio.us, so we can make use of existing browser integration


## [Unreleased]

### Added
- 'lightblue' theme

### Changed
- Fixed theming of browser chrome in mobile browsers
- Changed link colour of 'dark' theme from blue to orange
- Modified card padding so it fits more content


## [1.1.0] - 2017-07-22

### Added
- Show 404 page if bookmark is not found when editing
- Cache buster to force loading of the latest styling
- Theming support, default is 'green'
- Themes need an extra `theme` field in the User table
- Added 'freshgreen' and 'dark' themes

### Changed
- Make running in a virtualenv optional
- Fix for misalignment and size of hamburger icon
- Updated Python (pip) dependencies
- Updated MaterializeCSS and jQuery

### Removed
- Removed dependency on more_itertools
- Removed dependency on utilkit


## [1.0.0] - 2016-12-29

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


## [0.2.0] - 2016-08-02

- Favicon courtesy Freepik on flaticon.com
- Tag tags for easy adding of tags
- Updates to MaterializeCSS and jQuery
- Several bug- and code style fixes
- Styling tweaks
- Added 'Add bookmark' FAB to the bookmarks overview
- Option to strip parameters from url (like '?utm_source=social')


## [0.1.0] - 2016-07-26

- Initial release
- Flask application with functionality to add users, add and edit bookmarks,
  tag bookmarks, group by tags, create tag-based public pages (read-only, to be shared
  with interested parties)
