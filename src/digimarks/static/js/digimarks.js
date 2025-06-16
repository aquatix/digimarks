document.addEventListener('alpine:init', () => {
    Alpine.store('digimarks', {
        /** Main digimarks application, state etc */
        userKey: -1,
        /* cache consists of cache[userKey] = {'bookmarks': [], 'tags': [], ??} */
        cache: Alpine.$persist({}).as('cache'),

        bookmarks: [],

        /* nebula (drop-shadows), bbs (monospace, right lines), silo (like bbs but dark) ?? */
        themes: ['nebula', 'nebula-dark', 'bbs', 'silo'],
        theme: Alpine.$persist('nebula').as('theme'),

        showBookmarks: Alpine.$persist(true).as('showBookmarks'),
        showBookmarksList: Alpine.$persist(true).as('showBookmarksList'),
        showBookmarksCards: Alpine.$persist(false).as('showBookmarksCards'),
        showTags: Alpine.$persist(false).as('showTags'),
        /* Bookmark that is being edited, used to fill the form, etc. */
        bookmarkToEdit: Alpine.$persist(null).as('bookmarkToEdit'),

        /* Loading indicator */
        loading: false,

        /* Search filter */
        search: '',
        /* Show bookmarks with this tag/these tags */
        tagsFilter: [],
        /* Hide bookmarks with these tags */
        tagsToHide: Alpine.$persist([]).as('tags_to_hide'),

        /* Sort on ~ */
        sortTitleAsc: Alpine.$persist(false).as('sortTitleAsc'),
        sortTitleDesc: Alpine.$persist(false).as('sortTitleDesc'),
        sortCreatedAsc: Alpine.$persist(false).as('sortCreatedAsc'),
        sortCreatedDesc: Alpine.$persist(false).as('sortCreatedDesc'),

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

            let latestStatusResponse = await fetch('/api/v1/' + this.userKey + '/latest_changes/');
            let latestStatusResult = await latestStatusResponse.json();
            let shouldFetch = false;
            let latestModificationInCache = this.cache[this.userKey].latest_changes.latest_modification || "0000-00-00";
            shouldFetch = latestStatusResult.latest_modification > latestModificationInCache;
            this.cache[this.userKey].latest_changes = latestStatusResult;

            if (!shouldFetch) {
                console.log('Cache is up-to-date');
                this.loading = false;
                return;
            }

            console.log('Fetching latest bookmarks from backend for user "' + this.userKey + '"...');
            /* At the moment, request 'a lot' bookmarks; likely all of them in one go; paging tbd if needed */
            let response = await fetch('/api/v1/' + this.userKey + '/bookmarks/?limit=10000');
            /* Cache the bookmarks to Local Storage */
            this.cache[this.userKey]['bookmarks'] = await response.json();

            let tagsResponse = await fetch('/api/v1/' + this.userKey + '/tags/');
            this.cache[this.userKey]['tags'] = await tagsResponse.json();

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
            let prefilteredBookmarks = [...this.cache[this.userKey]['bookmarks']] || [];
            if (this.tagsToHide.length > 0) {
                console.log('Filtering away bookmarks containing blacklisted tags');
                this.bookmarks = prefilteredBookmarks.filter(
                    i => !this.hasTag(i.tag_list, this.tagsToHide)
                )
            } else {
                this.bookmarks = prefilteredBookmarks;
            }
            this.sortBookmarks();
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

        sortBookmarks() {
            /* Sort the bookmarks according to the setting */
            if (this.sortTitleAsc) {
                this.bookmarks.sort((a, b) => a.title.localeCompare(b.title));
            } else if (this.sortTitleDesc) {
                this.bookmarks.sort((a, b) => b.title.localeCompare(a.title));
            } else if (this.sortCreatedAsc) {
                this.bookmarks.sort((a, b) => a.created_date.localeCompare(b.created_date));
            } else if (this.sortCreatedDesc) {
                this.bookmarks.sort((a, b) => b.created_date.localeCompare(a.created_date));
            }
        },
        async sortAlphabetically(order = 'asc') {
            /* Sort the bookmarks (reverse) alphabetically, based on 'asc' or 'desc' */
            this.loading = true;
            this.sortCreatedAsc = false;
            this.sortCreatedDesc = false;
            this.sortTitleAsc = false;
            this.sortTitleDesc = false;
            if (order === 'desc') {
                this.sortTitleDesc = true;
            } else {
                this.sortTitleAsc = true;
            }
            this.sortBookmarks();
            this.loading = false;
        },
        async sortCreated(order = 'asc') {
            /* Sort the bookmarks (reverse) chronologically, based on 'asc' or 'desc' */
            this.loading = true;
            this.sortCreatedAsc = false;
            this.sortCreatedDesc = false;
            this.sortTitleAsc = false;
            this.sortTitleDesc = false;
            if (order === 'desc') {
                this.sortCreatedDesc = true;
            } else {
                this.sortCreatedAsc = true;
            }
            this.sortBookmarks();
            this.loading = false;
        },

        async toggleTagPage() {
            /* Show or hide the tag page instead of the bookmarks */
            this.showBookmarks = !this.showBookmarks;
            this.showTags = !this.showBookmarks;
        },
        async toggleListOrGrid() {
            /* Toggle between 'list' or 'grid' (cards) view */
            this.showBookmarksList = !this.showBookmarksList;
            this.showBookmarksCards = !this.showBookmarksList;
        },

        async startAddingBookmark() {
            /* Open 'add bookmark' page */
            console.log('Start adding bookmark');
            this.bookmarkToEdit = {
                'url': ''
            }
            // this.show_bookmark_details = true;
            const editFormDialog = document.getElementById("editFormDialog");
            editFormDialog.showModal();
        },
        async saveBookmark() {
            console.log('Saving bookmark');
            // this.show_bookmark_details = false;
        },
        async addBookmark() {
            /* Post new bookmark to the backend */
            //
        }
    })
});
