/** Found pictures used on the landing page. Each one is credited in the footer. */
export type Credit = { title: string; creator: string; license: string; page: string; usedFor: string };

export const CREDITS: Credit[] = [
  {
    title: "Skyline of Bandar Lampung from Bukit Randu Hotel",
    creator: "Firzafp",
    license: "CC BY-SA 4.0",
    page: "https://commons.wikimedia.org/w/index.php?curid=89654418",
    usedFor: "siger di pembuka",
  },
  {
    title: "Jalan Pangeran Antasari - Bandar Lampung",
    creator: "Firzafp",
    license: "CC BY-SA 4.0",
    page: "https://commons.wikimedia.org/w/index.php?curid=90502945",
    usedFor: "bagian tentang",
  },
  {
    title: "Ground Level View of Jalan Teknika Selatan",
    creator: "Joaquim Baeta",
    license: "CC BY 4.0",
    page: "https://commons.wikimedia.org/wiki/File:Ground_Level_View_of_Jalan_Teknika_Selatan.webm",
    usedFor: "rekaman contoh di cara kerja",
  },
];
