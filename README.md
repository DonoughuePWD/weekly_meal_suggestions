**Weekly meal suggestions**



A small Python script that emails weekly dinner suggestions based on a curated list of recipe links, so we don't have to think too hard about what we're going to eat each week. 



The Python script:



\- Reads recipe URLs from `recipes.txt` (My list has been developed by my wife and I over a decade; feel free to use it, or substitute with your own.)

\- Uses GPT-5.2 to suggest dinners and a non-staples shopping list based on considering the URL segment (it assumes you've got stapes like butter, olive oil etc)

\- Sends the result via email (scheduled externally; I'm using Task Scheduler in Windows but you might use a different option)



FYI:

Secrets (email password, OpenAI API key) are provided via environment variables so they are not in the repo. You'll need to set up a .cmd file with global variables (e.g. your email, recipient's email, OpenAI API key etc).

**If you don't care for the technical details and just want to use it:**

-- create a recipes.txt file in a folder and chuck your fave URLs in
-- create a .cmd file in a folder and fill in the env variables (e.g. API key, email, password etc)
-- put those two files and the weekly_meal_plan_llm_v2.py in the same place
-- download the latest version of Python
-- Use Task Scheduler (on Windows) or a similar automation tool to grab your script and .cmd file and run them on a weekly schedule
-- no longer be stuck on what to cook! 



