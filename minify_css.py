from csscompressor import compress
with open('static/style.css', 'r') as css:
	css_string = css.read()
	css_string_minified = compress(css_string)
	css.close()
with open('static/style.css', 'w') as css:
	css.write(css_string_minified)
	css.close()