document.addEventListener('alpine:init', () => {
    Alpine.store('digimarks', {
        /** Main digimarks application, state etc */
        // userKey: Alpine.$persist(0).as('userKey'),
        userKey: -1,
        /* cache consists of cache[userKey] = {'bookmarks': [], 'tags': [], ??} */
        cache: Alpine.$persist({}).as('cache'),

        bookmarks: [],

        /* Bookmark that is being edited, used to fill the form etc */
        bookmark_to_edit: null,

        /* nebula (dropshadows), bbs (monospace, right lines), silo (like bbs but dark) ?? */
        themes: ['nebula', 'nebula-dark', 'bbs', 'silo'],
        theme: Alpine.$persist('nebula').as('theme'),

        show_bookmarks: Alpine.$persist(true).as('show_bookmarks'),
        show_bookmarks_list: Alpine.$persist(true).as('show_bookmarks_list'),
        show_bookmarks_cards: Alpine.$persist(false).as('show_bookmarks_cards'),
        show_tags: Alpine.$persist(false).as('show_tags'),

        /* Loading indicator */
        loading: false,

        /* Search filter */
        search: '',
        /* Show bookmarks with this tag/these tags */
        tags_filter: [],
        /* Hide bookmarks with these tags */
        tags_to_hide: Alpine.$persist([]).as('tags_to_hide'),

        /* Sort on ~ */
        sort_title_asc: Alpine.$persist(false).as('sort_title_asc'),
        sort_title_desc: Alpine.$persist(false).as('sort_title_desc'),
        sort_created_asc: Alpine.$persist(false).as('sort_created_asc'),
        sort_created_desc: Alpine.$persist(false).as('sort_created_desc'),

        async init() {
            /** Initialise the application after loading */
            document.documentElement.setAttribute('data-theme', this.theme);
            console.log('Set theme', this.theme);
            /* Bookmarks are refreshed through the getBookmarks() call in the HTML page */
            /* await this.getBookmarks(); */
            setInterval(() => {
                // Update counter to next game (midnight UTC, fetched from API) every second
                // this.countDownTimer();
            }, 1000);
        },

        async loopToNextTheme() {
            /* Loop through themes */
            let currentThemeIndex = this.themes.indexOf(this.theme);
            if (currentThemeIndex + 1 >= this.themes.length) {
                currentThemeIndex = 0
            } else {
                currentThemeIndex++;
            }
            this.theme = this.themes[currentThemeIndex];
            console.log('Switching to theme', this.theme)
            document.documentElement.setAttribute('data-theme', this.theme);
            /* Optionally, change the theme CSS file too */
            // document.getElementById('theme-link').setAttribute('href', 'digui-theme-' + this.theme + '.css');
        },

        async loadCache() {
            /* Load bookmarks and tags from cache */
            if (this.userKey in this.cache) {
                console.log('Loading bookmarks from cache for user "' + this.userKey + '"');
                this.filterBookmarksByTags();
            }
        },
        async getBookmarks() {
            /** Get the bookmarks from the backend */
            this.loading = true;
            if (!(this.userKey in this.cache)) {
                /* There is no cache for this userKey yet, create on */
                console.log('Creating cache for user "' + this.userKey + '"');
                this.cache[this.userKey] = {'bookmarks': [], 'latest_changes': {}};
            }

            let latest_status_response = await fetch('/api/v1/' + this.userKey + '/latest_changes/');
            let latest_status_result = await latest_status_response.json();
            let should_fetch = false;
            let latest_modification_in_cache = this.cache[this.userKey].latest_changes.latest_modification || "0000-00-00";
            should_fetch = latest_status_result.latest_modification > latest_modification_in_cache;
            this.cache[this.userKey].latest_changes = latest_status_result;

            if (!should_fetch) {
                console.log('Cache is up-to-date');
                this.loading = false;
                return;
            }

            console.log('Fetching latest bookmarks from backend for user "' + this.userKey + '"...');
            /* At the moment, request 'a lot' bookmarks; likely all of them in one go; paging tbd if needed */
            let response = await fetch('/api/v1/' + this.userKey + '/bookmarks/?limit=10000');
            /* Cache the bookmarks to Local Storage */
            this.cache[this.userKey]['bookmarks'] = await response.json();

            let tags_response = await fetch('/api/v1/' + this.userKey + '/tags/');
            this.cache[this.userKey]['tags'] = await tags_response.json();

            /* Filter bookmarks by (blacklisted) tags */
            await this.filterBookmarksByTags();
            this.loading = false;
        },

        hasTag(tagList, filterList) {
            /* Looks for the items in filterList and returns True when one appears on the tagList */
            if (tagList === undefined) {
                return false;
            }
            for (let tag in filterList) {
                if (tagList.includes(tag))
                    return true;
            }
            return false;
        },
        filterBookmarksByTags() {
            /* Filter away bookmarks with a tag on the 'blacklist' */

            /* First make a shallow copy of all bookmarks */
            let prefiltered_bookmarks = [...this.cache[this.userKey]['bookmarks']] || [];
            if (this.tags_to_hide.length > 0) {
                console.log('Filtering away bookmarks containing blacklisted tags');
                this.bookmarks = prefiltered_bookmarks.filter(
                    i => !this.hasTag(i.tag_list, this.tags_to_hide)
                )
            } else {
                this.bookmarks = prefiltered_bookmarks;
            }
        },
        get filteredBookmarks() {
            /* Get the bookmarks, optionally filtered by search text or tag black-/whitelists */

            /* Use 'bookmarks' and not the cache, as it can already be pre-filtered */
            if (this.search === '') {
                /* No need to filter, quickly return the set */
                return this.bookmarks;
            }
            return this.bookmarks.filter(
                i => i.title.match(new RegExp(this.search, "i"))
            )
        },
        get filteredTags() {
            /* Search in the list of all tags */
            return this.cache[this.userKey].tags.filter(
                i => i.match(new RegExp(this.search, "i"))
            )
        },

        async sortAlphabetically(order = 'asc') {
            /* Sort the bookmarks (reverse) alphabetically, based on 'asc' or 'desc' */
            this.loading = true;
            this.sort_created_asc = false;
            this.sort_created_desc = false;
            this.sort_title_asc = false;
            this.sort_title_desc = false;
            if (order === 'desc') {
                this.sort_title_desc = true;
                this.bookmarks.sort((a, b) => b.title.localeCompare(a.title));
            } else {
                this.sort_title_asc = true;
                this.bookmarks.sort((a, b) => a.title.localeCompare(b.title));
            }
            this.loading = false;
        },
        async sortCreated(order = 'asc') {
            /* Sort the bookmarks (reverse) chronologically, based on 'asc' or 'desc' */
            this.loading = true;
            this.sort_created_asc = false;
            this.sort_created_desc = false;
            this.sort_title_asc = false;
            this.sort_title_desc = false;
            if (order === 'desc') {
                this.sort_created_desc = true;
                this.bookmarks.sort((a, b) => b.created_date.localeCompare(a.created_date));
            } else {
                this.sort_created_asc = true;
                this.bookmarks.sort((a, b) => a.created_date.localeCompare(b.created_date));
            }
            this.loading = false;
        },

        async toggleTagPage() {
            /* Show or hide the tag page instead of the bookmarks */
            console.log('Toggle tag page');
            this.show_bookmarks = !this.show_bookmarks;
            this.show_tags = !this.show_bookmarks;
        },
        async toggleListOrGrid() {
            /* Toggle between 'list' or 'grid' (cards) view */
            this.show_bookmarks_list = !this.show_bookmarks_list;
            this.show_bookmarks_cards = !this.show_bookmarks_list;
        },

        async startAddingBookmark() {
            /* Open 'add bookmark' page */
            console.log('Start adding bookmark');
            this.bookmark_to_edit = {
                'url': ''
            }
        },
        async addBookmark() {
            /* Post new bookmark to the backend */
            //
        }
    })
});
