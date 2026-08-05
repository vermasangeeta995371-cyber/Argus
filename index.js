// Minimal discord.js v14 bot with a prefix command and a slash command template
// Run: npm install
// Create .env with DISCORD_TOKEN and optionally GUILD_ID for dev guild command registration

require("dotenv").config();
const { Client, GatewayIntentBits, Routes, REST, SlashCommandBuilder } = require("discord.js");

const token = process.env.DISCORD_TOKEN;
const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent]
});

client.once("ready", () => {
  console.log(`Logged in as ${client.user.tag}`);
});

// Prefix command example
client.on("messageCreate", message => {
  if (message.author.bot) return;
  if (!message.content.startsWith("!")) return;

  const args = message.content.slice(1).trim().split(/\s+/);
  const cmd = args.shift().toLowerCase();

  if (cmd === "ping") {
    message.channel.send("Pong! :ping_pong:");
  }
});

// Slash command registration (dev guild preferred)
const commands = [
  new SlashCommandBuilder().setName("hello").setDescription("Say hello")
].map(cmd => cmd.toJSON());

const rest = new REST({ version: "10" }).setToken(token);

(async () => {
  try {
    console.log("Registering slash commands...");
    if (process.env.GUILD_ID) {
      await rest.put(Routes.applicationGuildCommands(process.env.CLIENT_ID, process.env.GUILD_ID), { body: commands });
      console.log("Registered in dev guild.");
    } else {
      await rest.put(Routes.applicationCommands(process.env.CLIENT_ID), { body: commands });
      console.log("Registered globally (may take up to an hour).");
    }
  } catch (err) {
    console.error(err);
  }
})();

client.on("interactionCreate", async interaction => {
  if (!interaction.isChatInputCommand()) return;
  if (interaction.commandName === "hello") {
    await interaction.reply(`Hello, ${interaction.user.username}!`);
  }
});

client.login(token);