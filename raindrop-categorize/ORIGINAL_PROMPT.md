## Skill Overview

If a skill named "raindrop-categorize" is available, ask if it needs to be updated or improved. If the user answers 'no', you are done for now.

Since we don't have the agent we want, create one. Take the existing agent, if any, and use it as a starting point.

The goal is to make a self-improving skill that can categorize raindrop data. The skill should have clear measures of quality and completeness for the process, and should be able to improve its performance over time.

The rough process desired is described below. Feel free to adapt this process as needed when implementing and/or improving the skill.

## Process

1. Read the existing set of Collections and build a tree that maps each Collection to its id.
2. Read the list of Tags.
3. Find the list of new Raindrops (aka bookmarks) to be processed (limited to at most 100 Raindrops). A Raindrop should be processed if one or more of the following is true:
   - The Raindrop has no Collection or is in "Unsorted"
   - The Raindrop has no Tags
   - The Raindrop has no Description or Note field
4. If there are less than 100 new Raindrops to process, fill the remaining slots in the list with the Raindrops that were the least recently processed.
5. Process each Raindrop in the list to update/create its Collection, Tags, Note, and Description, using the Processing steps described below. Before starting the processing, and after completing it, score the results quality on completeness, succintenss, appropriate tone, and relevance.
6. If there are any Raindrops that have need new Tags or Collections to be created, present the list to me as a CSV file with columns for the Raindrop name, url, description, and one column per tag/collection (titled with the field contents, prefixed with 'C-' for Collection and 'T-' for Tag). Then ask the user to fill out the CSV file and tell you when they are done.
7. Create all approved Tags and Collections from the CSV file. Delete the CSV file only if there are no more rows to process.

### Processing the Collection Field

If there is no Collection assigned, use the Description and/or Note fields to determine a suitable Collection. If neither is available, first write a Note using the process described in the "Processing the Description and Notes Fields" section below. Then use the Note to determine a suitable Collection. If no suitable Collection can be determined, save the Raindrop to a memory or todo list that will persist across sessions and mark it as needed a new Collection named "x".

### Processing the Tags Field

As with the Collection field, we want to assign one or more Tags to the Raindrop. Follow the process above to handle assigning these Tags, including processing the Description and Notes fields to determine a suitable Tag if need be. If a suitable Tag does not exist, put it in the memory or todo list that will persist across sessions and mark it as needing a new Tag named "y".

### Processing the Description and Notes Fields

The description field of a Raindrop _may_ contain a handwritten description of the content at the Raindrop's URL and its significance to the user, or it might be an AI generated description that Raindrop itself created, or it could be empty. The content of handwritten descriptions should be preserved as much as possible, but it is allowed to add to and reword that description as long as no meaningful content is lost. Existing content in the Note field should be replaced with the updated description, and the Description field contents should be removed. The end result should be a single clean, updated Note field and an empty Description field.

## Improving

When you are done processing the list of Raindrops, evaluate the lists of Collections and Tags including any newly created ones. Determine if there are any Collections or Tags that are redundant or that could be more clearly named, whether the Collection could be better served by a new or different parent Collection, or if any Tags are not being used effectively.
