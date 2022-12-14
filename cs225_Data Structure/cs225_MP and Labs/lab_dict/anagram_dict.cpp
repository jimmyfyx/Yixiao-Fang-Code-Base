/**
 * @file anagram_dict.cpp
 * Implementation of the AnagramDict class.
 *
 * @author Matt Joras
 * @date Winter 2013
 */

#include "anagram_dict.h"

#include <algorithm> /* I wonder why this is included... */
#include <fstream>

using std::string;
using std::vector;
using std::ifstream;

/**
 * Constructs an AnagramDict from a filename with newline-separated
 * words.
 * @param filename The name of the word list file.
 */
AnagramDict::AnagramDict(const string& filename)
{
    ifstream wordsFile(filename);
    string word;
    if (wordsFile.is_open()) 
    {
        /* Reads a line from `wordsFile` into `word` until the file ends. */
        while (getline(wordsFile, word)) 
        {
            string sort_word = word;
            std::sort(sort_word.begin(), sort_word.end());
            dict[sort_word].push_back(word);
        }
    }
}

/**
 * Constructs an AnagramDict from a vector of words.
 * @param words The vector of strings to be used as source words.
 */
AnagramDict::AnagramDict(const vector<string>& words)
{
    for (unsigned int i = 0; i < words.size(); i ++)
    {
        string sort_word = words[i];
        std::sort(sort_word.begin(), sort_word.end());
        dict[sort_word].push_back(words[i]);
    }
}

/**
 * @param word The word to find anagrams of.
 * @return A vector of strings of anagrams of the given word. Empty
 * vector returned if no anagrams are found or the word is not in the
 * word list.
 */
vector<string> AnagramDict::get_anagrams(const string& word) const
{
    string sort_word = word;
    std::sort(sort_word.begin(), sort_word.end());
    if (dict.find(sort_word) == dict.end())
    {
        return vector<string>();
    }
    return dict.at(sort_word);
}

/**
 * @return A vector of vectors of strings. Each inner vector contains
 * the "anagram siblings", i.e. words that are anagrams of one another.
 * NOTE: It is impossible to have one of these vectors have less than
 * two elements, i.e. words with no anagrams are ommitted.
 */
vector<vector<string>> AnagramDict::get_all_anagrams() const
{
    vector<vector<string>> ret;
    for (auto it = dict.begin(); it != dict.end(); it ++)
    {
        if ((it -> second).size() >= 2)
        {
            ret.push_back(it -> second);
        }
    }
    return ret;
}
