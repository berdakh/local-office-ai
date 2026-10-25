{% if scripture is defined and scripture.context %}
Scripture referenced in this sermon, checked against the World English Bible.
Quote scripture only from this list, word for word. A reference marked NOT FOUND
is probably a mis-hearing in the transcript; mention the reference but do not
quote it.
{{ scripture.context }}

{% endif %}
