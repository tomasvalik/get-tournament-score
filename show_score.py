#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 26 19:20:54 2024

@author: tomasvalik
"""

import pandas as pd
import re
import streamlit as st
import os


# %% HELPER FUNCTIONS

def is_place_difference(line):
    return line.isdigit()

def locate_line(content, keyword):
    for i, line in enumerate(content):
        if keyword in line:
            return i
    return -1

def parse_tournament_details(content):
    index = locate_line(content, "TIER")
    if index == -1:
        index = locate_line(content, "MAJOR")
    if index == -1:
        raise ValueError("Tournament details not found")
    return content[index + 1:index + 4]

def parse_round_info(content):
    index = locate_line(content, "RD 1")
    if index == -1:
        raise ValueError("Round information not found")
    return content[index + 3]  # Round info appears after RD1, RD2, RD3

def parse_player_data(content, is_first_round=False):
    rows = []
    i = 0
    while i < len(content):
        try:
            placement = content[i]
            i += 1
            
            if i < len(content) and is_place_difference(content[i]):
                i += 1
            
            name = content[i]
            
            if is_first_round:
                round_score = content[i + 1]
                total_score = round_score  # For Round 1, "Total Score" is the same as "Round Score"
                i += 3  # Move to the hole scores
            else:
                total_score = content[i + 1]
                round_score = content[i + 2]
                i += 4  # Move to the hole scores
                
            hole_scores = content[i:i+18]
            i += 18  # Skip the hole scores
            
            rating = content[i + 1]
            i += 2  # Move past the rating
            
            rows.append({
                "Place": placement,
                "Name": name,
                "Total Score": total_score,
                "Round Score": round_score,
                "Hole Scores": hole_scores,
                "Rating": rating
            })
        except IndexError:
            break
        
    return pd.DataFrame(rows)

def parse_all_player_data(content):
    round_dfs = []
    start_index = 0
    rounds_parsed = 0

    while start_index < len(content):
        # Locate the start of player data
        all_players_index = locate_line(content[start_index:], "ALL PLAYERS")
        if all_players_index == -1:
            break
        start_index += all_players_index + 1

        # Locate the end of player data
        end_index_relative = locate_line(content[start_index:], "COLOR ACCESSIBILITY")
        if end_index_relative == -1:
            raise ValueError("End of player data not found for one of the rounds")
        end_index = start_index + end_index_relative

        # Extract and parse this round's data
        round_data = content[start_index:end_index]
        is_first_round = (rounds_parsed == 0)  # First round has no Total Score
        round_df = parse_player_data(round_data, is_first_round=is_first_round)
        round_df["Name"] = round_df["Name"].apply(add_space_to_name)
        round_dfs.append(round_df)

        # Move the index forward to start after the current round
        start_index = end_index + 1
        rounds_parsed += 1
    
    return round_dfs

def parse_course_info(content):
    index = locate_line(content, "Thru")
    if index == -1:
        raise ValueError("Course information not found")
    course_info_data = content[index + 1:index + 1 + 18 * 3]  # 18 holes with 3 fields each
    hole_numbers, lengths, pars = [], [], []
    for i in range(0, len(course_info_data), 3):
        try:
            hole_numbers.append(course_info_data[i])
            lengths.append(course_info_data[i + 1])
            pars.append(course_info_data[i + 2])
        except IndexError:
            break
    
    return pd.DataFrame({
        "Hole Number": hole_numbers,
        "Length (m)": lengths,
        "Par": pars}
        )
    

def add_space_to_name(name):
    return re.sub(r'([a-záéíóúýčďěňřšťžů])([A-ZÁÉÍÓÚÝČĎĚŇŘŠŤŽŮ])', r'\1 \2', name)

def add_hole_status(player_df, course_df):
    
    par_values = course_df['Par'].astype(int).tolist()
    score_map = {
        -4: "CONDOR", -3: "ALBATROSS", -2: "EAGLE", -1: "BIRDIE", 0: "PAR", 
        1: "BOGEY", 2: "DBL BOGEY", 3: "TRPL BOGEY", 4: "4x BOGEY", 5: "5x BOGEY"
    }
    
    hole_diff = []
    hole_status = []
    for scores in player_df['Hole Scores']:
        diffs = []
        statuses = []
        for score, par in zip(scores, par_values):
            # Handle invalid score (non-numeric values like 'F', 'X', etc.)
            try:
                score_int = int(score)
            except ValueError:
                score_int = 999  # You can change this to any default value or treatment for non-numeric scores
                
            diff = score_int - par
            diffs.append(diff)
            statuses.append(
                "HOLE IN ONE" if (diff == -2 and par == 3) or (diff == -3 and par == 4) 
                else score_map.get(diff, f"{diff}x BOGEY")
            )
        hole_diff.append(diffs)
        hole_status.append(statuses)
    
    player_df['Hole Diff'] = hole_diff
    player_df['Hole Status'] = hole_status
    return player_df

def parse_data(content):
    cleaned_content = [line.strip() for line in content if line.strip()]
    cleaned_content = [line for line in cleaned_content if not line.startswith("CASH LINE")]

    # Extract tournament details
    tournament_details = parse_tournament_details(cleaned_content)

    # Extract round info
    round_info = parse_round_info(cleaned_content)

    # Extract course info
    course_df = parse_course_info(cleaned_content)

    # Extract player data for all rounds
    player_dfs = parse_all_player_data(cleaned_content)

    return course_df, player_dfs, tournament_details, round_info

@st.cache_data
def cached_parse_data(file):
    return parse_data(file)

def get_start_scores(player_df):
    if not isinstance(player_df, pd.DataFrame):
        raise ValueError("player_df is not a DataFrame. Received type: {}".format(type(player_df)))
    
    if 'Total Score' not in player_df.columns or 'Round Score' not in player_df.columns:
        raise KeyError("Missing required columns in player_df: 'Total Score' or 'Round Score'")

    player_df['Total Score'] = pd.to_numeric(player_df['Total Score'].replace("E", "0"), errors='coerce')
    player_df['Round Score'] = pd.to_numeric(player_df['Round Score'].replace("E", "0"), errors='coerce')
    player_df['Start Score'] = player_df['Total Score'] - player_df['Round Score']
    return player_df[['Name', 'Start Score']]

def get_score_midround(player_df, hole_num, course_df):

    player_df = add_hole_status(player_df, course_df)
    
    start_scores = get_start_scores(player_df).copy()
    
    if hole_num == 0:
        start_scores.loc[:, 'Total'] = start_scores['Start Score']
        start_scores.loc[:, 'Rd'] = 0  
        start_scores.loc[:, 'Hole Scores'] = [[] for _ in range(len(start_scores))]
        standings_df = start_scores.sort_values(by='Total').reset_index(drop=True)

    else:
        cumulative_scores = []
        round_scores = []
        hole_scores_upto_hole_num = []
        hole_status_upto_hole_num = []
    
        for start_score, hole_diff, hole_scores, hole_status in zip(
            start_scores['Start Score'], 
            player_df['Hole Diff'],
            player_df['Hole Scores'], 
            player_df['Hole Status']
        ):
            total_diff = sum(hole_diff[:hole_num])
            cumulative_score = start_score + total_diff
            
            round_score = cumulative_score - start_score
    
            cumulative_scores.append(cumulative_score)
            round_scores.append(round_score)
            hole_scores_upto_hole_num.append(hole_scores[:hole_num])
            hole_status_upto_hole_num.append(hole_status[:hole_num])
    
        start_scores.loc[:, 'Total'] = cumulative_scores
        start_scores.loc[:, 'Rd'] = round_scores  # Add Round Score column
        start_scores.loc[:, 'Hole Scores'] = hole_scores_upto_hole_num
        start_scores.loc[:, 'Hole Status'] = hole_status_upto_hole_num
    
        standings_df = start_scores.sort_values(by=['Total', 'Rd','Name'], ascending=[True, True, True]).reset_index(drop=True)


    standings_df['Total'] = standings_df['Total'].fillna(999)
    standings_df['Rd'] = standings_df['Rd'].fillna(999)

    standings_df['Total'] = standings_df['Total'].astype(int)
    standings_df['Rd'] = standings_df['Rd'].astype(int)


    # Rank players based on Total, using 'min' method for ties
    standings_df['Place'] = standings_df['Total'].rank(method='min', ascending=True).astype(int)

    # Now, we handle the formatting of the 'Place' column, including "T" for tied places
    standings_df['Place'] = standings_df['Place'].apply(
        lambda x: f"T{x}" if standings_df['Place'].value_counts()[x] > 1 else str(x)
    )

    standings_df['Total'] = standings_df['Total'].apply(
        lambda x: "DNF" if x == 999 else (f"E" if x == 0 else (f"+{x}" if x > 0 else str(x)))
    )
    
    standings_df['Rd'] = standings_df['Rd'].apply(
        lambda x: "DNF" if x == 999 else (f"E" if x == 0 else (f"+{x}" if x > 0 else str(x)))
    )
    
    return standings_df[["Place", "Name", 'Total', "Rd", "Hole Scores"]]
    

def load_tournament_mapping(file_path):
    mapping = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                # Split each line into key-value pairs by the colon
                if ":" in line:
                    file_name, display_name = line.split(":", 1)
                    # Clean and strip quotes/spaces
                    file_name = file_name.strip().strip('"')
                    display_name = display_name.strip().strip('"')
                    mapping[file_name] = display_name
    except FileNotFoundError:
        st.error(f"Mapping file '{file_path}' not found.")
    return mapping

# %% MAIN FUNCTION

def main():
    st.set_page_config(page_title="Disc Golf Tournament", layout="wide")
    
    data_folder = "data"
    mapping_file = "tournament_names.txt"
    
    tournament_mapping = load_tournament_mapping(mapping_file)

    available_files = [
        file for file in os.listdir(data_folder) if file.endswith(".csv")
    ]
    
    available_files = sorted(available_files, reverse=True)

    dropdown_list = []
    current_year = None

    for file in available_files:
        year = file.split("_")[0]  # Extract the year from the filename
        if year != current_year:
            dropdown_list.append(f"--- {year} ---")  # Add a header for the year
            current_year = year
        dropdown_list.append(file)  # Add the tournament file

    selected_option = st.selectbox(
        "Select a tournament you'd like to display:",
        options=dropdown_list,
        format_func=lambda x: tournament_mapping.get(x, x) if not x.startswith("---") else x,
    )

    if not selected_option or selected_option.startswith("---"):
        st.warning("Please select a valid tournament, not a year header.")
        return

    selected_file = selected_option
    file_path = os.path.join(data_folder, selected_file)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.readlines()

    course_df, player_dfs, tournament_details, round_info = parse_data(content)

    st.title(tournament_mapping.get(selected_file, "Tournament Details"))
    st.markdown(f":date: {tournament_details[1]}, :round_pushpin: {tournament_details[2]}")
            
    file_path = os.path.join(data_folder, selected_file)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.readlines()
    
    st.divider()

    round_options = {i: f"Round {i+1}" for i in range(len(player_dfs))}
    selected_round = st.segmented_control(
        "Select a round/hole",
        options=round_options.keys(),
        format_func=lambda x: round_options[x],
        selection_mode="single",
        default=0
    )
    if selected_round is None:
        selected_round = 0

    
    hole_options = {i: f'{i}' for i in range(0, 19)}  # Mapping for holes 1 to 18
    selected_hole = st.segmented_control(
        "Select a hole",
        options=hole_options.keys(),
        format_func=lambda option: hole_options[option],
        selection_mode="single",
        default=18,
        label_visibility="collapsed"
    )
    if selected_hole is None:
        selected_hole = 18

    st.subheader(
        "Standings Before the Round" if selected_hole == 0 else 
        (f"Standings After {selected_hole} holes" if selected_hole < 18 else "Final Standings")
    )

    player_df = player_dfs[selected_round]
    
    if not isinstance(player_df, pd.DataFrame):
        st.error("Error: Selected round does not contain valid player data.")
    else:
        standings_df = get_score_midround(player_df, selected_hole, course_df)
        st.dataframe(standings_df, hide_index=True)

    st.divider()

    st.subheader("Course Information")
    
    transposed_course_df = course_df.T.drop(index='Hole Number')
    transposed_course_df.index = ["Length", "Par"]
    transposed_course_df.columns = [f"{i+1}" for i in range(transposed_course_df.shape[1])]
    transposed_course_df = transposed_course_df.apply(pd.to_numeric, errors='coerce')
    
    total_length, total_par = transposed_course_df.loc["Length"].sum(), transposed_course_df.loc["Par"].sum()
    
    st.markdown(f" :straight_ruler: **Length:**  {total_length} m, :flying_disc: **Par:**  {total_par}")

    st.dataframe(transposed_course_df, hide_index=False)

    st.divider()

    st.subheader("Download Assets")
    
    st.download_button(
        label="Download Standings as CSV",
        data=standings_df.to_csv(index=False),
        file_name=f"standings_rd{selected_round+1}h{selected_hole}.csv",
        mime="text/csv"
    )
    
    st.download_button(
        label="Download Course Info as CSV",
        data=course_df.to_csv(index=False),
        file_name="course_info.csv",
        mime="text/csv"
    )



# %%

if __name__ == "__main__":
    main()


# %%

