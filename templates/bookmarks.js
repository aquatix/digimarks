var elem = document.querySelector('.autocomplete');
var instance = M.Autocomplete.getInstance(elem);
instance.updateData({
    {% for bookmark in bookmarks %}
        {% if bookmark.favicon %}
            "{{ bookmark.title | replace('"', '\\"') | replace('\n', '') | replace('\r', '') }}": "{{ url_for('static', filename='favicons/' + bookmark.favicon) }}",
        {% else %}
            "{{ bookmark.title | replace('"', '\\"') | replace('\n', '') | replace('\r', '') }}": null,
        {% endif %}
    {% endfor %}
});
