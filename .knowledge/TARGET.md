First you need to get where all existing cards are from .searchable .knowledge-bck and other places in the repo. 

We need to migrate them to our target card system. See specs/013 for the shape and schema for the cards and event and system mechanism i had. 


Following is the folder structure I want

.knowledge
- architecture
- cards
- .stage <-- delta changes will live here first before added into cards or architecture and LLM will ask user to approve those changes. 
- INDEX.md <-- will hold all cards name - {one line description}
- ARCHITECTURE.md <-- will hold base architecture and modules in it and explain what velocity is
- state.yaml <-- for tracking when knowledge was synced date+commit-ref 


Skills
Only one skill /velocity with params like following
/velocity analyze / fix / sync / prime / book-keeping

Skill directory would have 
SKILL.md <-- /velocity skill 
skill will redirect to the sub skill md for each 
sync.md <-- It will see state.yaml get the commit and date and see what has been updated after that date and commit and stage all delta changes (from cards, architecture, commits) to .stage and ask user to approve or if user have set explicitly in frontmatter of sync like auto-approve-staged-changes: true to automatically be added into cards and architecture. After sync it will automatically call prime. 
prime.md <-- Prime will first check if CONTEXT.md is there and up to date based on frontmatter of context. if stale by comparing  CONTEXT with state.yaml last sync commit. It will rebuild the CONTEXT and CONTEXT will have INDEX.md compacted and ARCHITECTURE.md COMPACTED with code base tree so that useable by agents and explaination what velocity is.  
analyze.md <-- will use prime -> read INDEX.md find symptom links -> ARCHITECTURE -> Investigate exact issue rootcause and report back, Prompt user to ADD it in the JIRA if they want it if yes use mcp to add new ticket with descriptions and show to user and if approved create it. also call book-keeping at end 
fix.md <-- will use analyze to find rootcause -> then see what is the fix under ARCHTIECTure etc and share blast radius of it and what issues it can have as sideeffect then if user approves do that fix. also do book-keeping at end.  
book-keeping.md <-- will only add cards or architecture based on user query. 



Ignore CARDEX totally we are not building it rather we are doing a pivot to decrease the scope and deliver it faster

Please use sub agents of type SONNET or HAIKU to do trivial work and then validate it. Do not do trivial things on your own. Migrate all cards to the target architecture and create full archtiecture what we need context pack skills etc. Do not leave things in middle and think it end to end. 