**Weekly meal suggestions**



A small Python script that emails weekly dinner suggestions based on a curated list of recipe links, so we don't have to think too hard about what we're going to eat each week. 



The Python script:



\- Reads recipe URLs from `recipes.txt` (My list has been developed by my wife and I over a decade; feel free to use it, or substitute with your own.)

\- Uses GPT-5.2 to suggest dinners and a non-staples shopping list based on considering the URL segment (it assumes you've got stapes like butter, olive oil etc)

\- Sends the result via email (scheduled externally; I'm using Task Scheduler in Windows but you might use a different option)



FYI:

Secrets (email password, OpenAI API key) are provided via environment variables so they are not in the repo.



