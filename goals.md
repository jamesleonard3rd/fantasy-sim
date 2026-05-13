Each entity has a hierarchical goal system managed by a GoalBrain. Goals have priorities (1–5), urgency, deadlines, interruptibility, and optional subgoals. The scheduler continuously evaluates all valid goals using a dynamic score (priority + urgency + deadline pressure − cost/danger) to determine the active goal.

Goals are divided into:

Survival/need goals (eat, sleep, flee, heal) that can temporarily override other goals
Long-term goals (travel, join faction, enter tournament, train)
Immediate action goals (move, attack, interact, wait)

Goals may contain subgoals with different completion modes:

ordered: must be completed sequentially
any_order: can be completed in any order
all_required: all required but order flexible
optional: improve outcome but not mandatory

Long-term goals decompose into smaller actionable goals. Example:
Enter Tournament →

Travel to city
Register
Rest
Compete

Goals support pausing/resuming so entities can interrupt long-term tasks when urgent needs arise, then continue afterward.

Architecture:

Goal system decides what the entity wants
Planner/subgoal system determines steps
Behavior tree/state machine executes current actions

This creates persistent, reactive AI capable of balancing immediate needs with long-term ambitions.