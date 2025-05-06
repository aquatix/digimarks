document.addEventListener('alpine:init', () => {
    Alpine.store('digimarks', {
        /** Main digimarks application, state etc */
        // userKey: Alpine.$persist(0).as('userKey'),
        userKey: -1,
        /* cache consists of cache[userKey] = {'bookmarks': [], 'tags': [], ??} */
        cache: Alpine.$persist({}).as('cache'),

        bookmarks: [],
        tags: [],

        /* Loading indicator */
        loading: false,

        /* Search filter */
        search: '',

        /* Sort on ~ */
        sort_title_asc: Alpine.$persist(false).as('sort_title_asc'),
        sort_title_desc: Alpine.$persist(false).as('sort_title_desc'),
        sort_created_asc: Alpine.$persist(false).as('sort_created_asc'),
        sort_created_desc: Alpine.$persist(false).as('sort_created_desc'),

        async init() {
            /** Initialise the application after loading */
            // if (this.userKey in this.cache) {
            //     console.log('loading bookmarks from cache');
            //     this.bookmarks = this.cache[this.userKey]['bookmarks'] || [];
            // }
            /* await this.getBookmarks(); */
            setInterval(() => {
                // Update counter to next game (midnight UTC, fetched from API) every second
                // this.countDownTimer();
            }, 1000);
        },
        async loadCache() {
            if (this.userKey in this.cache) {
                console.log('Loading bookmarks from cache for user "' + this.userKey + '"');
                this.bookmarks = this.cache[this.userKey]['bookmarks'] || [];
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
            let response = await fetch('/api/v1/' + this.userKey + '/bookmarks/?limit=10000');
            let result = await response.json();
            this.bookmarks = result;
            /* Cache the bookmarks to Local Storage */
            this.cache[this.userKey]['bookmarks'] = result;

            let tags_response = await fetch('/api/v1/' + this.userKey + '/tags/');
            let tags_result = await tags_response.json();
            this.cache[this.userKey]['tags'] = tags_result;

            this.loading = false;
        },
        get filteredBookmarks() {
            // return this.cache[this.userKey]['bookmarks'].filter(
            //     i => i.title.includes(this.search)
            // )
            /* Use 'bookmarks' as it can already be pre-filtered */
            return this.bookmarks.filter(
                i => i.title.match(new RegExp(this.search, "i"))
            )
        },
        get filteredTags() {
            return this.cache[this.userKey].tags.filter(
                i => i.match(new RegExp(this.search, "i"))
            )
        },
        async sortAlphabetically(order = 'asc') {
            if (order === 'desc') {
                this.bookmarks.sort((a, b) => b.title.localeCompare(a.title));
            } else {
                this.bookmarks.sort((a, b) => a.title.localeCompare(b.title));
            }
        },
        async sortCreated(order = 'asc') {
            if (order === 'desc') {
                this.bookmarks.sort((a, b) => b.created_date.localeCompare(a.created_date));
            } else {
                this.bookmarks.sort((a, b) => a.created_date.localeCompare(b.created_date));
            }
        }
    })
});
