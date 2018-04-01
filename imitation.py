import os
import argparse
import numpy as np
import keras
import gym
from keras.utils import plot_model
import matplotlib.pyplot as plt
from keras.callbacks import TensorBoard
import tensorflow as tf


class Imitation:
    def __init__(self, args):
        # Load the expert model.
        with open(args.model_config_path, 'r') as f:
            self.expert = keras.models.model_from_json(f.read())
        self.expert.load_weights(args.expert_weights_path)
        # plot_model(self.expert, to_file='expert_model.png')

        # Initialize the cloned model (to be trained).
        with open(args.model_config_path, 'r') as f:
            self.model = keras.models.model_from_json(f.read())
        # plot_model(self.expert, to_file='clone_model.png')

        self.num_episodes = args.num_episodes
        self.num_epochs = args.num_epochs
        self.eval_episodes = args.eval_episodes

        # Define any training operations and optimizers here, initialize your variables,
        # or alternatively compile your model here.
        self.model.compile(loss=keras.losses.categorical_crossentropy,
                           optimizer=keras.optimizers.Adam(lr=args.base_lr, beta_1=0.9, beta_2=0.999, epsilon=None,
                                                           decay=0.0, amsgrad=False),
                           metrics=['acc'])

    def run_expert(self, env, render=False):
        """
        Generates an episode by running the expert policy on the given env.
        :param env: 
        :param render: 
        :return: 
        """
        return Imitation.generate_episode(self.expert, env, render)

    def run_model(self, env, render=False):
        """
        Generates an episode by running the cloned policy on the given env.
        :param env: 
        :param render: 
        :return: 
        """
        states, _, rewards = Imitation.generate_episode(self.model, env, render)
        expert_actions = []
        for s in states:
            one_hot_expert_action = np.zeros(env.action_space.n)
            one_hot_expert_action[np.argmax(self.expert.predict(np.expand_dims(s, axis=0)))] = 1
            expert_actions.append(one_hot_expert_action)
        return states, expert_actions, rewards

    @staticmethod
    def generate_episode(model, env, render=False):
        """
        Generates an episode by running the given model on the given env.
        :param model: 
        :param env: 
        :param render: 
        :return: 
            - a list of states, indexed by time step
            - a list of actions, indexed by time step
            - a list of rewards, indexed by time step
        """
        states = []     # (episode_length, 8)
        actions = []    # (episode_length, 8) -> one-hot encoding
        rewards = []    # (episode_length,)

        observation = env.reset()

        if render:
            env.render()

        while True:
            action = np.argmax(model.predict(np.expand_dims(observation, axis=0)))
            observation, reward, done, _ = env.step(action)
            if render:
                env.render()
            if done:
                break
            one_hot_action = np.zeros(env.action_space.n)
            one_hot_action[action] = 1
            states.append(observation)
            actions.append(one_hot_action)
            rewards.append(reward)
        return states, actions, rewards
    
    def train(self, env, log_dir, num_episodes=100, num_epochs=50, render=False):
        """
        Trains the model on training data generated by the expert policy.
        :param env: The environment to run the expert policy on. 
        :param log_dir: 
        :param num_episodes: # episodes to be generated by the expert.
        :param num_epochs: # epochs to train on the data generated by the expert.
        :param render: Whether to render the environment.
        :return: the final loss and accuracy.
        """
        train_states = np.zeros([0, env.observation_space.shape[0]], dtype=float)
        train_actions = np.zeros([0, env.action_space.n], dtype=int)

        # get training data from expert
        for j in range(num_episodes):
            states, actions, rewards = self.run_expert(env, render)
            train_states = np.concatenate([train_states, np.array(states)], axis=0)
            train_actions = np.concatenate([train_actions, np.array(actions)], axis=0)

        # train current model from training data
        history = self.model.fit(train_states, train_actions, batch_size=32, epochs=num_epochs, verbose=1)

        # save model and weights
        if not os.path.isdir('model'):
            os.mkdir('model')
        file_name = "model/{}.h5".format(log_dir)
        self.model.save_weights(file_name)

        # save loss
        if not os.path.isdir('loss'):
            os.mkdir('loss')
        loss_name = "loss/{}.txt".format(log_dir)
        with open(loss_name, 'w') as file_to_write:
            file_to_write.write("{}".format(','.join(str(k) for k in history.history['loss'])))

        # save accuracy
        if not os.path.isdir('acc'):
            os.mkdir('acc')
        acc_name = "acc/{}.txt".format(log_dir)
        with open(acc_name, 'w') as file_to_write:
            file_to_write.write("{}".format(','.join(str(k) for k in history.history['acc'])))

        return history.history['loss'][0], history.history['acc'][0]

    def evaluate(self, env, log_dir, eval_episodes=50, render=False):
        expert_rewards = []
        rewards = []

        # expert
        for i in range(eval_episodes):
            total_reward = 0.
            observation = env.reset()
            if render:
                env.render()
            while True:
                action = np.argmax(self.expert.predict(np.expand_dims(observation, axis=0)))
                observation, reward, done, _ = env.step(action)
                if render:
                    env.render()
                if done:
                    break
                total_reward += reward
            expert_rewards.append(total_reward)

        # learnt
        self.model.load_weights("model/{}.h5".format(log_dir))
        for i in range(eval_episodes):
            total_reward = 0.
            observation = env.reset()
            if render:
                env.render()
            while True:
                action = np.argmax(self.model.predict(np.expand_dims(observation, axis=0)))
                observation, reward, done, _ = env.step(action)
                if render:
                    env.render()
                if done:
                    break
                total_reward += reward
            rewards.append(total_reward)

        print("Expert Policy: mean: %f std: %f" % (np.mean(np.array(expert_rewards)), np.std(np.array(expert_rewards))))
        print("Cloned Policy: mean: %f std: %f" % (np.mean(np.array(rewards)), np.std(np.array(rewards))))

    @staticmethod
    def plot(log_dir):
        loss_name = "loss/{}.txt".format(log_dir)
        loss_list = np.loadtxt(loss_name, delimiter=',')
        plt.plot(loss_list)
        plt.title('training loss')
        plt.ylabel('loss')
        plt.xlabel('number of epochs')
        plt.show()

        acc_name = "acc/{}.txt".format(log_dir)
        acc_list = np.loadtxt(acc_name, delimiter=',')
        plt.plot(acc_list)
        plt.title('training accuracy')
        plt.ylabel('accuracy')
        plt.xlabel('number of epochs')
        plt.show()
        pass


def parse_arguments():
    # Command-line flags are defined here.
    parser = argparse.ArgumentParser()
    parser.add_argument('--num_episodes', type=int, help="number of episodes to be generated by the expert")
    parser.add_argument('--log_dir', type=str, help='log directory where the checkpoints and summaries are saved.')
    parser.add_argument('--train', action='store_true', help='turn on training mode')
    parser.add_argument('--test', action='store_true', help='turn on test mode')
    parser.add_argument('--plot', action='store_true', help='turn on plotting')
    parser.add_argument('--num_epochs', type=int, default=100, help='number of epochs for training')
    parser.add_argument('--eval_episodes', type=int, default=50, help='number of evaluation episodes')
    parser.add_argument('--base_lr', type=float, default=0.001, help='initial learning rate')
    parser.add_argument('--model-config-path', dest='model_config_path', type=str, default='LunarLander-v2-config.json',
                        help="Path to the model config file.")
    parser.add_argument('--expert-weights-path', dest='expert_weights_path', type=str,
                        default='LunarLander-v2-weights.h5', help="Path to the expert weights file.")

    # https://stackoverflow.com/questions/15008758/parsing-boolean-values-with-argparse
    parser_group = parser.add_mutually_exclusive_group(required=False)
    parser_group.add_argument('--render', dest='render', action='store_true', help="Whether to render the environment.")
    parser_group.add_argument('--no-render', dest='render', action='store_false',
                              help="Whether to render the environment.")
    parser.set_defaults(render=False)

    return parser.parse_args()


def main(args):
    # Create the environment.
    env = gym.make('LunarLander-v2')

    imitation = Imitation(args)

    if args.train:
        imitation.train(env, args.log_dir, args.num_episodes, args.num_epochs, args.render)
    elif args.test:
        imitation.evaluate(env, args.log_dir, args.eval_episodes)
    elif args.plot:
        imitation.plot(args.log_dir)

if __name__ == '__main__':
    # Parse command-line arguments.
    args = parse_arguments()
    main(args)