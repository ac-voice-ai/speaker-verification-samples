# Copyright (C) 2021 AudioCodes Ltd.
from enum import Enum
from botbuilder.core import ActivityHandler, TurnContext, ConversationState, MessageFactory
from botbuilder.schema import Activity, ActivityTypes


# Speaker verification modes
class Mode(str, Enum):
    TEXT_INDEPENDENT = 'text-independent',
    TEXT_DEPENDENT = 'text-dependent'


# Choose the bot mode. Can be configured by the user to TEXT_INDEPENDENT or TEXT_DEPENDENT
bot_mode = Mode.TEXT_INDEPENDENT


# Bot can be in several states during the flow, the following are the use-cases:
# Example 1: NOT_ENROLLED -> ENROLLMENT_PROCESS -> End Of Conversation
# Example 2: ENROLLED -> VERIFICATION_PROCESS -> End Of Conversation
# Example 3: ENROLLED -> ASKED_FOR_DELETION -> DELETION_PROCESS -> End Of Conversation

# Short phases explanation:
# NOT_ENROLLED = The user isn't enrolled in the speaker verification system
# ENROLLED = The user is enrolled and been asked now for an action to do (verification\deletion)
# ENROLLMENT_PROCESS = The user said 'yes' when he was asked for enrollment, now he's been asked for collecting his voice
# VERIFICATION_PROCESS = The user said 'yes' when he was asked for verification, now he's been asked for collecting his voice
# ASKED_FOR_DELETION = The user said 'yes'\'no' when he was asked to delete his voiceprint
# DELETION_PROCESS = The user said 'yes' when he was asked for deletion, now he's waiting for the action result
class Phase(Enum):
    NOT_ENROLLED = 0,
    ENROLLED = 1,
    ENROLLMENT_PROCESS = 2,
    VERIFICATION_PROCESS = 3,
    DELETION_PROCESS = 4,
    ASKED_FOR_DELETION = 5


class ConversationData:
    def __init__(
        self,
        phase: Phase = Phase.NOT_ENROLLED,
        speaker_id: str = None
    ):
        self.phase = phase
        self.speaker_id = speaker_id


class MyBot(ActivityHandler):
    def __init__(self, conversation_state: ConversationState):
        self.conversation_state = conversation_state
        self.mode = bot_mode
        self.sentencesState = {  # For independent mode, define the questionnaire for collecting long audio
            'currSentence': 0,
            'sentences': [
                'Please describe yourself.',
                'Please tell me about your hobbies.',
                'Can you tell me about your work experience?',
                'Can you tell me about your education?',
                'Can you tell me about your family?',
                'In the battle of life and death, who do you think will win, Superman or Batman? Please explain.',
                'Can you tell me one good thing and one bad thing about yourself?',
                'What is your favorite movie and why?',
                'What kind of food do you like?'
            ]
        }
        self.conversation_data_accessor = self.conversation_state.create_property(
            "ConversationData")

    def getSentenceToPrompt(self, default_sentence):
        nextSentence = self.sentencesState['sentences'][self.sentencesState['currSentence']
                                                        ] if self.mode is Mode.TEXT_INDEPENDENT else default_sentence
        return nextSentence

    def setNextSentenceIfNeeded(self):
        if self.mode is Mode.TEXT_INDEPENDENT:
            self.sentencesState['currSentence'] = (
                self.sentencesState['currSentence'] + 1) % len(self.sentencesState['sentences'])

    async def send_end_of_conversation_activity(self, turn_context: TurnContext, reason: str):
        await turn_context.send_activity(MessageFactory.text(reason))
        return await turn_context.send_activity(Activity(type=ActivityTypes.end_of_conversation))

    async def send_clarification_activity(self, turn_context: TurnContext, text="Sorry, I didn't understand you. Please say yes or no."):
        return await turn_context.send_activity(MessageFactory.text(text))

    async def on_turn(self, turn_context: TurnContext):
        await super().on_turn(turn_context)
        # Save any state changes that might have ocurred during the turn.
        await self.conversation_state.save_changes(turn_context)

    async def on_event_activity(self, turn_context: TurnContext):
        conversation_data = await self.conversation_data_accessor.get(turn_context, ConversationData)
        evname = turn_context.activity.name.lower()
        evvalue = turn_context.activity.value
        evchanneldata = turn_context.activity.channel_data
        print('------------------------------------------------------------')
        print(f'evname --- {evname}')
        print(f'evvalue --- {evvalue}')
        print(f'evchanneldata --- {evchanneldata}')
        print('------------------------------------------------------------')

        if evname == "channel" and str(evvalue).lower() == "telephony":
            conversation_data.speaker_id = evchanneldata['caller']
            ac_activity_params = {
                "speakerVerificationSpeakerId": conversation_data.speaker_id}
            event_value = {"sessionParams": ac_activity_params}
            ac_activity = Activity(
                type=ActivityTypes.event, name="speakerVerificationGetSpeakerStatus", channel_data=event_value)
            await turn_context.send_activity(ac_activity)
            return await turn_context.send_activity(MessageFactory.text("Hi, welcome to the verifier bot"))

        elif evname == "speakerverificationspeakerstatus":
            conversation_data.phase = Phase.ENROLLED if evvalue['enrolled'] else Phase.NOT_ENROLLED
            text = "What would you like to do?" if evvalue[
                'enrolled'] else "You are currently not enrolled. Do you concent to enroll?"
            return await turn_context.send_activity(MessageFactory.text(text))

        elif evname == "speakerverificationenrollprogress":
            if evvalue['moreAudioRequired']:  # Speaker is not enrolled yet
                nextSentence = self.getSentenceToPrompt(
                    "One more time, please say your passphrase")
                self.setNextSentenceIfNeeded()

                return await turn_context.send_activity(MessageFactory.text(nextSentence))
            else:  # Speaker is enrolled
                # To throw an error?
                return

        elif evname == "speakerverificationverifyprogress":
            if evvalue['moreAudioRequired']:  # Speaker is not verified yet
                nextSentence = self.getSentenceToPrompt(
                    "One more time, please say your passphrase")
                self.setNextSentenceIfNeeded()

                return await turn_context.send_activity(MessageFactory.text(nextSentence))
            else:  # Speaker is verified
                # To throw an error?
                return

        elif evname == "speakerverificationenrollcompleted":
            if evvalue['success']:
                await turn_context.send_activity(MessageFactory.text("You have been enrolled successfully"))
                return await self.send_end_of_conversation_activity(turn_context, "I will hang up now. For a verification process please make another call.")
            else:
                self.send_end_of_conversation_activity(
                    turn_context, "There was some problem with the enrollment, please try again in another call. Goodbye")

        elif evname == "speakerverificationverifycompleted":
            reason = "You have been verified successfully. Thanks and goodbye" if evvalue[
                'success'] else "Sorry, you are not who you say you are, Goodbye"
            return await self.send_end_of_conversation_activity(turn_context, reason)

        elif evname == "speakerverificationactionresult" and conversation_data.phase == Phase.DELETION_PROCESS:
            reason = "You have been deleted. For more actions please make another call, goodbye" if evvalue[
                'success'] else "You have not been deleted for some error, Goodbye"
            return await self.send_end_of_conversation_activity(turn_context, reason)

        else:
            print('Do nothing')
            return

    async def on_message_activity(self, turn_context: TurnContext):
        conversation_data = await self.conversation_data_accessor.get(turn_context, ConversationData)
        if conversation_data.phase == Phase.NOT_ENROLLED:  # Not enrolled
            if turn_context.activity.text == 'Yes.':
                conversation_data.phase = Phase.ENROLLMENT_PROCESS
                ac_activity_params = {"speakerVerificationType": self.mode.value,
                                      "speakerVerificationSpeakerId": conversation_data.speaker_id}
                event_value = {"sessionParams": ac_activity_params}
                ac_activity = Activity(
                    type=ActivityTypes.event, name="speakerVerificationEnroll", channel_data=event_value)
                await turn_context.send_activity(ac_activity)

                sentenceToPrompt = self.getSentenceToPrompt(
                    "Please say your passphrase")
                self.setNextSentenceIfNeeded()

                return await turn_context.send_activity(MessageFactory.text(sentenceToPrompt))
            elif turn_context.activity.text == 'No.':
                return await self.send_end_of_conversation_activity(turn_context, "You chosed not to pass an enrollment. I will hangup now, goodbye")
            else:
                return await self.send_clarification_activity(turn_context)

        elif conversation_data.phase == Phase.ENROLLED:  # Already enrolled
            if 'delete' not in turn_context.activity.text.lower():
                conversation_data.phase = Phase.VERIFICATION_PROCESS
                ac_activity_params = {"speakerVerificationType": self.mode.value,
                                      "speakerVerificationSpeakerId": conversation_data.speaker_id}
                event_value = {"sessionParams": ac_activity_params}
                ac_activity = Activity(
                    type=ActivityTypes.event, name="speakerVerificationVerify", channel_data=event_value)
                await turn_context.send_activity(ac_activity)

                sentenceToPrompt = self.getSentenceToPrompt(
                    "For verification, please say your passphrase")
                self.setNextSentenceIfNeeded()

                return await turn_context.send_activity(MessageFactory.text(sentenceToPrompt))
            else:
                conversation_data.phase = Phase.ASKED_FOR_DELETION
                return await turn_context.send_activity(MessageFactory.text("Would you like to delete yourself?"))

        elif conversation_data.phase == Phase.ASKED_FOR_DELETION:
            if turn_context.activity.text == 'Yes.':
                conversation_data.phase = Phase.DELETION_PROCESS
                ac_activity_params = {
                    "speakerVerificationSpeakerId": conversation_data.speaker_id}
                event_value = {"sessionParams": ac_activity_params}
                ac_activity = Activity(
                    type=ActivityTypes.event, name="speakerVerificationDeleteSpeaker", channel_data=event_value)
                return await turn_context.send_activity(ac_activity)
                # ac_activity_params = {"enableSpeechInput": False}
                # event_value = {"activityParams": ac_activity_params}
                # ac_activity = Activity(
                #     type=ActivityTypes.message, text="Great, just a sec", channel_data=event_value)
                # return await turn_context.send_activity(ac_activity)
            elif turn_context.activity.text == 'No.':
                conversation_data.phase = Phase.ASKED_FOR_DELETION
                return await self.send_end_of_conversation_activity(turn_context, "You chosed not to delete yourself, Goodbye")
            else:
                return await turn_context.send_activity(MessageFactory.text("Sorry, I didn't understand you. Please say yes or no."))

        elif conversation_data.phase == Phase.ENROLLMENT_PROCESS:
            return
            # ac_activity_params = {"enableSpeechInput": False}
            # event_value = {"activityParams": ac_activity_params}
            # ac_activity = Activity(
            #     type=ActivityTypes.message, text="Great, just a sec", channel_data=event_value)
            # return await turn_context.send_activity(ac_activity)

        elif conversation_data.phase == Phase.VERIFICATION_PROCESS:
            return
            # ac_activity_params = {"enableSpeechInput": False}
            # event_value = {"activityParams": ac_activity_params}
            # ac_activity = Activity(
            #     type=ActivityTypes.message, text="Great, just a sec", channel_data=event_value)
            # return await turn_context.send_activity(ac_activity)

        else:
            return await turn_context.send_activity(MessageFactory.text("else not implemented yet"))

    # async def on_members_added_activity(
    #     self,
    #     members_added: ChannelAccount,
    #     turn_context: TurnContext
    # ):
    #     for member_added in members_added:
    #         if member_added.id != turn_context.activity.recipient.id:
    #             await turn_context.send_activity("Hello and welcome!")
