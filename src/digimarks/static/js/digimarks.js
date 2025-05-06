document.addEventListener('alpine:init', () => {
    Alpine.store('digimarks', {
        /** Main digimarks application, state etc */
        // userKey: Alpine.$persist(0).as('userKey'),
        userKey: -1,
        /* cache consists of cache[userKey] = {'bookmarks': [], 'tags': [], ??} */
        cache: Alpine.$persist({}).as('cache'),

        bookmarks: [],
        tags: [],

        tryout: 'hey',

        loading: false,

        search: '',

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
            console.log('Loading bookmarks from cache for user "' + this.userKey + '"');
            this.bookmarks = this.cache[this.userKey]['bookmarks'] || [];

        },
        async getBookmarks() {
            /** Get the bookmarks from the backend */
            this.loading = true;
            console.log('Fetching latest bookmarks from backend for user "' + this.userKey + '"...');
            let response = await fetch('/api/v1/' + this.userKey + '/bookmarks/?limit=10000');
            let result = await response.json();
            console.log(result);
            this.bookmarks = result;
            if (!(this.userKey in this.cache)) {
                /* There is no cache for this userKey yet, create on */
                console.log('caching');
                this.cache[this.userKey] = {'bookmarks': []};
            }
            /* Cache the bookmarks to Local Storage */
            this.cache[this.userKey]['bookmarks'] = result;
            this.loading = false;
        },
        get filteredItems() {
            // return this.cache[this.userKey]['bookmarks'].filter(
            //     i => i.title.includes(this.search)
            // )
            /* Use 'bookmarks' as it can already be pre-filtered */
            return this.bookmarks.filter(
                i => i.title.match(new RegExp(this.search, "i"))
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
